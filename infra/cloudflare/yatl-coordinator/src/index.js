const JSON_HEADERS = { "content-type": "application/json; charset=utf-8" };
const NODE_RE = /^NODE-[A-Z0-9][A-Z0-9_-]{1,31}$/;
const BATCH_RE = /^B\\d{3}$/;
const SHA_RE = /^[0-9a-f]{64}$/;
const DEFAULT_LEASE_SECONDS = 900;
const MAX_CLAIM_ATTEMPTS = 8;

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

async function sha256(text) {
  const bytes = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map(x => x.toString(16).padStart(2, "0")).join("");
}

function bearer(request) {
  const value = request.headers.get("authorization") || "";
  return value.startsWith("Bearer ") ? value.slice(7) : "";
}

async function parseJson(request) {
  try {
    const body = await request.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("invalid body");
    return body;
  } catch {
    throw new Response(JSON.stringify({ status: "BAD_REQUEST" }), {
      status: 400, headers: JSON_HEADERS,
    });
  }
}

async function adminAuthorized(request, env) {
  const token = bearer(request);
  if (!token || !env.YATL_ADMIN_TOKEN_SHA256) return false;
  return (await sha256(token)) === env.YATL_ADMIN_TOKEN_SHA256;
}

async function nodeAuthorized(request, env, nodeId) {
  if (!NODE_RE.test(nodeId)) return false;
  const token = bearer(request);
  if (!token) return false;
  const tokenHash = await sha256(token);
  const row = await env.DB.prepare(
    "SELECT token_sha256,enabled FROM nodes WHERE node_id=?1"
  ).bind(nodeId).first();
  return !!row && row.enabled === 1 && row.token_sha256 === tokenHash;
}

async function touchNode(env, nodeId, now) {
  await env.DB.prepare(
    "UPDATE nodes SET last_seen_ms=?1 WHERE node_id=?2"
  ).bind(now, nodeId).run();
}

async function event(env, type, nodeId, batchCode, payload, now) {
  await env.DB.prepare(
    "INSERT INTO events(event_ms,event_type,node_id,batch_code,payload_json) VALUES(?1,?2,?3,?4,?5)"
  ).bind(now, type, nodeId || null, batchCode || null, JSON.stringify(payload || {})).run();
}

async function planSha(env) {
  const row = await env.DB.prepare("SELECT value FROM meta WHERE key='plan_sha256'").first();
  return row?.value || null;
}

async function claimSpecific(env, nodeId, batchCode, leaseSeconds, now) {
  const until = now + leaseSeconds * 1000;
  const result = await env.DB.prepare(
    `UPDATE batches
       SET state='CLAIMED', owner_node=?1, lease_until_ms=?2, updated_at_ms=?3
       WHERE batch_code=?4
         AND state != 'INGESTED'
         AND state != 'AWAITING_INGEST'
         AND state != 'BLOCKED'
         AND (
           state='AVAILABLE'
           OR (state='CLAIMED' AND owner_node=?1)
           OR (state='CLAIMED' AND lease_until_ms < ?3)
         )`
  ).bind(nodeId, until, now, batchCode).run();
  if ((result.meta?.changes || 0) !== 1) return null;
  return await env.DB.prepare(
    "SELECT batch_code,batch_sha256,candidate_count,lease_until_ms FROM batches WHERE batch_code=?1"
  ).bind(batchCode).first();
}

async function claimAuto(env, nodeId, leaseSeconds, now) {
  for (let attempt = 0; attempt < MAX_CLAIM_ATTEMPTS; attempt++) {
    const candidate = await env.DB.prepare(
      `SELECT batch_code FROM batches
       WHERE state='AVAILABLE'
          OR (state='CLAIMED' AND lease_until_ms < ?1)
       ORDER BY batch_code LIMIT 1`
    ).bind(now).first();
    if (!candidate) return null;
    const claimed = await claimSpecific(env, nodeId, candidate.batch_code, leaseSeconds, now);
    if (claimed) return claimed;
  }
  return null;
}

async function handleClaim(request, env) {
  const body = await parseJson(request);
  const nodeId = String(body.node_id || "");
  if (!(await nodeAuthorized(request, env, nodeId))) return response({ status: "UNAUTHORIZED" }, 401);
  const leaseSeconds = Number(body.lease_seconds || DEFAULT_LEASE_SECONDS);
  if (!Number.isInteger(leaseSeconds) || leaseSeconds < 60 || leaseSeconds > 86400) {
    return response({ status: "INVALID_LEASE" }, 400);
  }
  const requested = body.batch_code == null ? null : String(body.batch_code);
  if (requested !== null && !BATCH_RE.test(requested)) return response({ status: "INVALID_BATCH" }, 400);
  const now = Date.now();
  await touchNode(env, nodeId, now);
  const claimed = requested
    ? await claimSpecific(env, nodeId, requested, leaseSeconds, now)
    : await claimAuto(env, nodeId, leaseSeconds, now);
  if (!claimed) return response({ status: requested ? "BATCH_UNAVAILABLE" : "NO_AVAILABLE_BATCH" }, 409);
  const plan = await planSha(env);
  const payload = {
    status: "BATCH_CLAIMED",
    plan_sha256: plan,
    node_id: nodeId,
    ...claimed,
  };
  await event(env, "BATCH_CLAIMED", nodeId, claimed.batch_code, payload, now);
  return response(payload);
}

async function handleHeartbeat(request, env) {
  const body = await parseJson(request);
  const nodeId = String(body.node_id || "");
  const batchCode = String(body.batch_code || "");
  if (!(await nodeAuthorized(request, env, nodeId))) return response({ status: "UNAUTHORIZED" }, 401);
  if (!BATCH_RE.test(batchCode)) return response({ status: "INVALID_BATCH" }, 400);
  const leaseSeconds = Number(body.lease_seconds || DEFAULT_LEASE_SECONDS);
  if (!Number.isInteger(leaseSeconds) || leaseSeconds < 60 || leaseSeconds > 86400) {
    return response({ status: "INVALID_LEASE" }, 400);
  }
  const now = Date.now();
  const until = now + leaseSeconds * 1000;
  const result = await env.DB.prepare(
    `UPDATE batches SET lease_until_ms=?1,updated_at_ms=?2
     WHERE batch_code=?3 AND state='CLAIMED' AND owner_node=?4 AND lease_until_ms>=?2`
  ).bind(until, now, batchCode, nodeId).run();
  if ((result.meta?.changes || 0) !== 1) return response({ status: "LEASE_LOST" }, 409);
  await touchNode(env, nodeId, now);
  return response({ status: "HEARTBEAT_ACCEPTED", node_id: nodeId, batch_code: batchCode, lease_until_ms: until });
}

async function handleRelease(request, env) {
  const body = await parseJson(request);
  const nodeId = String(body.node_id || "");
  const batchCode = String(body.batch_code || "");
  if (!(await nodeAuthorized(request, env, nodeId))) return response({ status: "UNAUTHORIZED" }, 401);
  if (!BATCH_RE.test(batchCode)) return response({ status: "INVALID_BATCH" }, 400);
  const now = Date.now();
  const result = await env.DB.prepare(
    `UPDATE batches SET state='AVAILABLE',owner_node=NULL,lease_until_ms=NULL,updated_at_ms=?1
     WHERE batch_code=?2 AND state='CLAIMED' AND owner_node=?3`
  ).bind(now, batchCode, nodeId).run();
  if ((result.meta?.changes || 0) !== 1) return response({ status: "RELEASE_REJECTED" }, 409);
  await event(env, "BATCH_RELEASED", nodeId, batchCode, {}, now);
  return response({ status: "BATCH_RELEASED", batch_code: batchCode });
}

async function handleReady(request, env) {
  const body = await parseJson(request);
  const nodeId = String(body.node_id || "");
  const batchCode = String(body.batch_code || "");
  const manifestSha = String(body.result_manifest_sha256 || "");
  const resultCount = Number(body.result_count);
  if (!(await nodeAuthorized(request, env, nodeId))) return response({ status: "UNAUTHORIZED" }, 401);
  if (!BATCH_RE.test(batchCode) || !SHA_RE.test(manifestSha) || !Number.isInteger(resultCount) || resultCount < 1) {
    return response({ status: "INVALID_READY_PAYLOAD" }, 400);
  }
  const now = Date.now();
  const result = await env.DB.prepare(
    `UPDATE batches SET state='AWAITING_INGEST',lease_until_ms=NULL,updated_at_ms=?1,
       result_manifest_sha256=?2,result_count=?3
     WHERE batch_code=?4 AND state='CLAIMED' AND owner_node=?5 AND candidate_count=?3`
  ).bind(now, manifestSha, resultCount, batchCode, nodeId).run();
  if ((result.meta?.changes || 0) !== 1) return response({ status: "READY_REJECTED" }, 409);
  await event(env, "BATCH_READY_FOR_INGEST", nodeId, batchCode, {
    result_manifest_sha256: manifestSha, result_count: resultCount,
  }, now);
  return response({ status: "BATCH_AWAITING_INGEST", batch_code: batchCode, result_manifest_sha256: manifestSha });
}

async function handleIngested(request, env) {
  if (!(await adminAuthorized(request, env))) return response({ status: "UNAUTHORIZED" }, 401);
  const body = await parseJson(request);
  const batchCode = String(body.batch_code || "");
  const manifestSha = String(body.result_manifest_sha256 || "");
  if (!BATCH_RE.test(batchCode) || !SHA_RE.test(manifestSha)) return response({ status: "INVALID_INGEST" }, 400);
  const now = Date.now();
  const result = await env.DB.prepare(
    `UPDATE batches SET state='INGESTED',owner_node=NULL,lease_until_ms=NULL,updated_at_ms=?1
     WHERE batch_code=?2 AND state='AWAITING_INGEST' AND result_manifest_sha256=?3`
  ).bind(now, batchCode, manifestSha).run();
  if ((result.meta?.changes || 0) !== 1) return response({ status: "INGEST_REJECTED" }, 409);
  await event(env, "BATCH_INGESTED", null, batchCode, { result_manifest_sha256: manifestSha }, now);
  return response({ status: "BATCH_INGESTED", batch_code: batchCode, result_manifest_sha256: manifestSha });
}

async function handleStatus(request, env) {
  const isAdmin = await adminAuthorized(request, env);
  const nodeId = request.headers.get("x-yatl-node") || "";
  const isNode = NODE_RE.test(nodeId) && await nodeAuthorized(request, env, nodeId);
  if (!isAdmin && !isNode) return response({ status: "UNAUTHORIZED" }, 401);
  const rows = await env.DB.prepare(
    `SELECT batch_code,state,owner_node,lease_until_ms,updated_at_ms,
            candidate_count,result_manifest_sha256,result_count
     FROM batches ORDER BY batch_code`
  ).all();
  const counts = {};
  for (const row of rows.results || []) counts[row.state] = (counts[row.state] || 0) + 1;
  const nodes = await env.DB.prepare(
    "SELECT node_id,enabled,max_workers,last_seen_ms FROM nodes ORDER BY node_id"
  ).all();
  return response({
    status: "COORDINATOR_STATUS",
    plan_sha256: await planSha(env),
    counts,
    batches: rows.results || [],
    nodes: nodes.results || [],
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return response({ status: "OK", service: "YATL_DISTRIBUTED_COORDINATOR" });
    }
    if (request.method === "POST" && url.pathname === "/v1/claim") return handleClaim(request, env);
    if (request.method === "POST" && url.pathname === "/v1/heartbeat") return handleHeartbeat(request, env);
    if (request.method === "POST" && url.pathname === "/v1/release") return handleRelease(request, env);
    if (request.method === "POST" && url.pathname === "/v1/ready") return handleReady(request, env);
    if (request.method === "POST" && url.pathname === "/v1/ingested") return handleIngested(request, env);
    if (request.method === "GET" && url.pathname === "/v1/status") return handleStatus(request, env);
    return response({ status: "NOT_FOUND" }, 404);
  },
};
