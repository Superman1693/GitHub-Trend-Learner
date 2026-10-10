"""GitHub-Trend-Learner 可视化控制台后端服务包。

分层约定：
    routes/      HTTP 路由层（只做参数解析与响应组装）
    services/    业务服务层（文档读取、任务执行，不含 HTTP 概念）
    http/        HTTP 基础设施（路由表、请求解析、响应封装、静态资源）
"""
__all__ = ["app"]
