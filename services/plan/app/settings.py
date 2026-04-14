from eligibility_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "plan"
    plan_cache_ttl_seconds: int = 300


settings = Settings()
