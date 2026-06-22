# Main Orchestrator는 adapters/supervisor.py(LangGraphSupervisor) + domain/services/
# supervisor_router.py(결정형 라우터)로 구현된다. 과거 application-layer
# RouteRequestUseCase는 어디에도 배선되지 않은 죽은 평행 구현이라 제거했다
# (supervisor-loop-architecture.md §9 P5). 본 패키지는 TASKS.md 스펙 보존용 빈 패키지다.
