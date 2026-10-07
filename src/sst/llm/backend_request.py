from typing import Any, Callable, Dict, List, Optional, Tuple


def execute_llm_backend_request(
    backend: str,
    model: str,
    messages: List[Dict[str, Any]],
    api_key: Optional[str],
    base_url: str,
    timeout: int,
    max_tokens: int,
    think: bool,
    url: Optional[str],
    headers: Dict[str, str],
    payload: Dict[str, Any],
    *,
    completion: Callable[..., Any],
    post: Callable[..., Any],
) -> Tuple[Dict[str, Any], int, str]:
    if backend == "LITELLM":
        sdk_response = completion(
            model=model,
            messages=messages,
            api_key=api_key or None,
            api_base=None if base_url.lower() == "auto" else base_url,
            timeout=timeout,
            temperature=0.0,
            max_tokens=max_tokens,
            extra_body={"think": think},
            drop_params=True,
            num_retries=0,
        )
        res_json = (
            sdk_response.model_dump()
            if hasattr(sdk_response, "model_dump")
            else dict(sdk_response)
        )
        return res_json, 200, ""

    if url is None:
        raise ValueError(f"No request URL configured for backend {backend}")
    response = post(url, headers=headers, json=payload, timeout=timeout)
    status_code = response.status_code
    res_json = response.json() if status_code == 200 else {}
    response_text = getattr(response, "text", "")
    return res_json, status_code, response_text