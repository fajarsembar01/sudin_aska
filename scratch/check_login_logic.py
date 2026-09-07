with open(
    r"c:\Users\sdnse\OneDrive\Dokumen\Yum\PROJEK SUDIN JU2\ASKA SUDIN JU 2\sudin_aska-2\dashboard\auth.py",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()

# find def login
start = content.find('@auth_bp.route("/login"')
if start != -1:
    print(content[start : start + 1800])
