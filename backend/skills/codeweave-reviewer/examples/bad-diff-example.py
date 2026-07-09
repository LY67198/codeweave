"""反面示例:Reviewer 看到这个 diff 应该 reject。

这个文件用作文档/教学用途,展示一个明显有安全问题的函数。
它不会被任何代码路径执行 — 只作为 Reviewer skill 训练/演示的素材。
"""


def user_login(username, password):
    """BAD:写死密码比对 + 拼 SQL。"""
    query = f"SELECT * FROM users WHERE name='{username}' AND pwd='{password}'"
    if query:
        return True
    return False


"""Reviewer 应该 reject(risk_flags: ['sql_injection', 'hardcoded_secret', 'no_hash'])"""
