import re

def latex_to_speech(text: str) -> str:
    """
    Converts LaTeX math expressions in text to readable Vietnamese speech.
    e.g., $\frac{7}{10}$ -> 7 phần 10
    """
    if not text:
        return text

    # Remove the $ delimiters if present
    # We will just process the whole text, assuming math expressions are identifiable,
    # or we can specifically target patterns within $.
    
    # Simple substitution rules
    # 1. Fractions: \frac{a}{b} -> a phần b
    text = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1 phần \2', text)
    
    # 2. Powers: x^2 -> x bình phương, x^3 -> x lập phương, x^n -> x mũ n
    text = re.sub(r'([a-zA-Z0-9_]+)\^2', r'\1 bình phương', text)
    text = re.sub(r'([a-zA-Z0-9_]+)\^3', r'\1 lập phương', text)
    text = re.sub(r'([a-zA-Z0-9_]+)\^([a-zA-Z0-9_]+|\{[^{}]+\})', r'\1 mũ \2', text)
    
    # Clean up { and } left by exponents like x^{10}
    text = text.replace('{', '').replace('}', '')
    
    # 3. Geometry/Symbols
    text = text.replace(r'\times', 'nhân')
    text = text.replace(r'\div', 'chia')
    text = text.replace(r'\ge', 'lớn hơn hoặc bằng')
    text = text.replace(r'\le', 'nhỏ hơn hoặc bằng')
    text = text.replace(r'\neq', 'khác')
    text = text.replace(r'\approx', 'xấp xỉ')
    text = text.replace(r'\+', 'cộng')
    text = text.replace(r'\-', 'trừ')
    
    # 4. Roots: \sqrt{x} -> căn bậc hai của x
    text = re.sub(r'\\sqrt\s*([a-zA-Z0-9_]+)', r'căn bậc hai của \1', text)
    
    # 5. Clean up $ signs
    text = text.replace('$', '')
    
    # Fix spacing
    text = re.sub(r'\s+', ' ', text).strip()
    return text

if __name__ == '__main__':
    tests = [
        r"Kết quả bằng $\frac{7}{10}$",
        r"Diện tích là $x^2 + y^2 = 25$",
        r"Khoảng cách $\approx 5km$",
        r"$\sqrt{16} \times 2 = 8$"
    ]
    for t in tests:
        print(f"Original: {t}")
        print(f"To Speech: {latex_to_speech(t)}\n")
