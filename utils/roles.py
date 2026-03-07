from database import get_cursor

def get_role(user_id):
    with get_cursor() as cur:
        cur.execute("SELECT role FROM users WHERE id=%s", (user_id,))
        result = cur.fetchone()
        return result[0] if result else 'user'

def set_user_role(user_id, role):
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET role=%s WHERE id=%s", (role, user_id))