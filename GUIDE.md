Đúng rồi, vẫn y xì như cũ! Gemma 4 MoE đã được khôi phục về config mạnh nhất. Đây là guide đầy đủ:

---

## 🔌 Thông số kết nối Gemma 4 MoE

| Thông số | Giá trị |
|---|---|
| **Model Name** | `gemma-4` |
| **API Key** | `gemma4-openclaw-2026` |
| **Context Window** | 49,152 tokens (~48K) |
| **Quantization** | NVFP4 (4-bit) |
| **GPU Memory** | 0.65 (~29 GB VRAM) |

---

### Cách gọi API (tuỳ vị trí service của bạn)

**1. Từ máy khác / PC cá nhân** (qua Nginx Gateway):
```
Base URL: http://171.226.10.121:8000/llm/v1
```

**2. Từ process chạy trực tiếp trên server L40S:**
```
Base URL: http://localhost:8080/v1
```

**3. Từ Docker container khác trên server L40S** (tối ưu nhất):
```
Base URL: http://gemma_4_moe:8000/v1
```
*(Container phải nằm trong network `web-network`)*

---

### Code mẫu Python (OpenAI-compatible)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://171.226.10.121:8000/llm/v1",  # Đổi tuỳ vị trí
    api_key="gemma4-openclaw-2026"
)

response = client.chat.completions.create(
    model="gemma-4",
    messages=[
        {"role": "system", "content": "Bạn là trợ lý AI thông minh."},
        {"role": "user", "content": "Xin chào!"}
    ],
    max_tokens=512,
    temperature=0.7
)

print(response.choices[0].message.content)
```

---

### Lệnh tắt/bật nhanh (trên server L40S)

```bash
# Tắt
docker stop gemma_4_moe

# Bật
docker start gemma_4_moe
```

Mọi thứ vẫn nguyên xi, không thay đổi gì so với trước khi thử Qwen nhé! 🚀