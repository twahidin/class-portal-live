"""
NanoBanana Pro API client for AI infographic generation.
Docs: https://docs.nanobananaapi.ai/
"""
import json
import time
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nanobananaapi.ai/api/v1/nanobanana"


def _request(api_key: str, path: str, method: str = "GET", body: dict = None) -> dict:
    """Send authenticated request to NanoBanana API."""
    url = f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            return json.loads(err_body)
        except Exception:
            return {"code": e.code, "message": str(e)}


def generate_pro(
    api_key: str,
    prompt: str,
    *,
    resolution: str = "2K",
    aspect_ratio: str = "4:3",
    image_urls: list = None,
) -> dict:
    """
    Submit a NanoBanana Pro image generation task.
    Returns {"code": 200, "data": {"taskId": "..."}} on success.
    callBackUrl is required by the API; we poll for result instead.
    """
    body = {
        "prompt": prompt[:4000],  # keep prompt within reason
        "resolution": resolution,
        "aspectRatio": aspect_ratio,
        "imageUrls": image_urls or [],
        "callBackUrl": "https://school-portal-callback.local/collab",  # required; we use polling
    }
    return _request(api_key, "/generate-pro", method="POST", body=body)


def get_task_details(api_key: str, task_id: str) -> dict:
    """
    Get task status and result.
    successFlag: 0=generating, 1=success, 2=create failed, 3=generate failed.
    On success, data.response.resultImageUrl contains the image URL.
    """
    return _request(api_key, f"/record-info?taskId={task_id}", method="GET")


def wait_for_result(api_key: str, task_id: str, max_wait_seconds: int = 120, poll_interval: float = 3.0) -> dict:
    """
    Poll until task completes or timeout.
    Returns {"success": True, "result_image_url": "..."} or {"success": False, "error": "..."}.
    """
    start = time.monotonic()
    while (time.monotonic() - start) < max_wait_seconds:
        resp = get_task_details(api_key, task_id)
        if resp.get("code") != 200:
            return {"success": False, "error": resp.get("message", "API error")}
        data = resp.get("data") or {}
        flag = data.get("successFlag", -1)
        if flag == 1:
            response = data.get("response") or {}
            url = response.get("resultImageUrl") or response.get("originImageUrl")
            if url:
                return {"success": True, "result_image_url": url}
            return {"success": False, "error": "No image URL in response"}
        if flag in (2, 3):
            return {"success": False, "error": data.get("errorMessage", "Generation failed")}
        time.sleep(poll_interval)
    return {"success": False, "error": "Timeout waiting for image generation"}
