import re
import time

def test_parse(text):
    text = text.replace("：", ":").replace("。", ".")
    parts = re.split(r"题目[:\s]+", text)
    new_questions = []
    
    for part in parts:
        if not part.strip():
            continue
            
        q_text_match = re.search(r"^(.*?)(?=[A-D][:.\s])", part, re.DOTALL)
        if not q_text_match:
            continue
        q_text = q_text_match.group(1).strip()
        
        options = {}
        for opt in ['A', 'B', 'C', 'D']:
            opt_match = re.search(fr"{opt}[:.\s]+(.*?)(?=[A-D][:.\s]|答案[:\s]|$)", part, re.DOTALL)
            if opt_match:
                options[opt] = opt_match.group(1).strip()
        
        ans_match = re.search(r"答案[:\s]+([A-D])", part, re.IGNORECASE)
        
        if q_text and len(options) == 4 and ans_match:
            new_questions.append({
                "id": int(time.time() * 1000) + len(new_questions),
                "text": q_text,
                "options": options,
                "answer": ans_match.group(1).upper()
            })
    return new_questions

test_text = """
题目：光合作用主要在细胞的哪个细胞器中进行？
A. 线粒体
B. 叶绿体
C. 核糖体
D. 内质网
答案：B

题目: 勾股定理中，直角三角形两条直角边的平方和等于斜边的平方。如果两直角边分别为3和4，斜边是多少?
A: 5
B: 6
C: 7
D: 8
答案: A
"""

results = test_parse(test_text)
print(f"Parsed {len(results)} questions")
for r in results:
    print(f"Q: {r['text']}")
    print(f"Options: {r['options']}")
    print(f"A: {r['answer']}")
    print("-" * 20)
