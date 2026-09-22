import json

from .acquisition import AcquisitionError, main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcquisitionError as exc:
        print(json.dumps({
            "code": "CRL002_ACQUISITION_ERROR",
            "reason": str(exc),
            "research_only": True,
            "p10_write_allowed": False,
            "p11_locked": True,
        }, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)
