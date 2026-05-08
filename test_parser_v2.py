import re
import time

def test_parse_v2(text):
    text = text.replace("：", ":").replace("．", ".").replace("。", ".")
    pattern = r"题目[:\s]*(.*?)\s*A[:.\s]+(.*?)\s*B[:.\s]+(.*?)\s*C[:.\s]+(.*?)\s*D[:.\s]+(.*?)\s*答案[:\s]*([A-D])"
    matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
    
    questions = []
    for match in matches:
        q_text, opt_a, opt_b, opt_c, opt_d, answer = match.groups()
        questions.append({
            "text": q_text.strip(),
            "options": {
                "A": opt_a.strip(),
                "B": opt_b.strip(),
                "C": opt_c.strip(),
                "D": opt_d.strip()
            },
            "answer": answer.strip().upper()
        })
    return questions

# 用户提供的无换行样例
user_sample = "题目：杭州千岛湖研学中，不包含的体验活动是？ A. 皮划艇水上体验B. 环湖骑行挑战C. 传统陶瓷拉坯制作D. 农夫山泉工厂参观答案：C"

# 混合多题样例
mixed_sample = """
题目：Q1 A. opt1 B. opt2 C. opt3 D. opt4 答案：C 
题目：Q2
A: 选项A
B: 选项B
C: 选项C
D: 选项D
答案: A
"""

print("--- Testing User Sample ---")
results1 = test_parse_v2(user_sample)
for r in results1:
    print(f"Q: {r['text']}")
    print(f"Opts: {r['options']}")
    print(f"Ans: {r['answer']}")

print("\n--- Testing Mixed Sample ---")
results2 = test_parse_v2(mixed_sample)
for r in results2:
    print(f"Q: {r['text']}")
    print(f"Ans: {r['answer']}")
