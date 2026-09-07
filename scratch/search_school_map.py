with open(
    r"c:\Users\sdnse\OneDrive\Dokumen\Yum\PROJEK SUDIN JU2\ASKA SUDIN JU 2\sudin_aska-2\dashboard\portal\routes.py",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()

start = content.find("def _fetch_user_school")
if start != -1:
    print(content[start : start + 1000])
else:
    # search globally
    print("Not found in portal/routes.py, let's search routes.py")
