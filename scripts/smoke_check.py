"""Bounded startup check; transient resets are not proof of an unhealthy service."""
import argparse
import http.client
import time
import urllib.error
import urllib.request


def wait_for_status(url, expected, *, attempts=60, pause=1, opener=urllib.request.urlopen, sleep=time.sleep):
    last = "no response"
    for attempt in range(attempts):
        try:
            with opener(url, timeout=2) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        except (OSError, http.client.HTTPException) as exc:
            last = type(exc).__name__
            if attempt + 1 < attempts:
                sleep(pause)
            continue
        if status == expected:
            return
        if status not in {500, 502, 503, 504}:
            raise RuntimeError(f"Expected HTTP {expected}; received HTTP {status}.")
        last = f"HTTP {status}"
        if attempt + 1 < attempts:
            sleep(pause)
    raise RuntimeError(f"Service did not become ready after {attempts} attempts ({last}).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-status", required=True, type=int)
    args = parser.parse_args()
    wait_for_status(args.url, args.expected_status)
    print(f"Startup check passed (HTTP {args.expected_status}).")


if __name__ == "__main__":
    main()
