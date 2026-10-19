import httpx

from app.config import Settings


class ModelError(RuntimeError):
    pass


class KimiClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chat(self, messages, temperature=0.1) -> str:
        cfg = self.settings
        if not cfg.llm_ready:
            raise ModelError("请在 .env 中配置 KIMI_API_KEY 和账号可用的 KIMI_MODEL。")
        try:
            with httpx.Client(timeout=cfg.llm_timeout_seconds) as client:
                response = client.post(
                    cfg.kimi_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.kimi_api_key}"},
                    json={"model": cfg.kimi_model, "messages": messages, "temperature": temperature},
                )
                response.raise_for_status()
                result = response.json()["choices"][0]["message"]["content"]
                if not isinstance(result, str) or not result.strip():
                    raise ValueError("empty completion")
                return result.strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            # 不把远端响应正文或认证头返回给浏览器。
            raise ModelError("模型调用失败，请检查服务地址、模型权限和网络连接。") from exc
