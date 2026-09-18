# Sentinel: is value ka matlab "practically unlimited" hai. Iske barabar
# limit pe hum mehnga COUNT query skip kar dete hain.
UNLIMITED = 999999

PLAN_LIMITS = {
    "free":     {"daily_calls": 999999, "total_calls": 100, "requests_per_minute": 10},
    "starter":  {"daily_calls": 5000,   "total_calls": 999999, "requests_per_minute": 30},
    "pro":      {"daily_calls": 50000,  "total_calls": 999999, "requests_per_minute": 100},
    "business": {"daily_calls": 500000, "total_calls": 999999, "requests_per_minute": 300},
}


def get_plan_limits(plan_name):
    return PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"])
