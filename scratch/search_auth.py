with open(
    r"c:\Users\sdnse\OneDrive\Dokumen\Yum\PROJEK SUDIN JU2\ASKA SUDIN JU 2\sudin_aska-2\dashboard\auth.py",
    "r",
    encoding="utf-8",
) as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "@" in line and "route" in line:
        print(f"{i+1}: {line.strip()}")
