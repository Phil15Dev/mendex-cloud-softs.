from app.core.ratelimit import make_limiter

login_by_user = make_limiter("login_user", 5)    # 5 failures per IP + username in 15 minutes
login_by_ip = make_limiter("login_ip", 20)       # 20 failures per IP in 15 minutes
reset_by_ip = make_limiter("reset_ip", 5)        # 5 reset requests per IP in 15 minutes
reauth = make_limiter("reauth", 5)               # 5 wrong passwords on sensitive actions in 15 minutes


def clear_all() -> None:
    for lim in (login_by_user, login_by_ip, reset_by_ip, reauth):
        lim.clear()
