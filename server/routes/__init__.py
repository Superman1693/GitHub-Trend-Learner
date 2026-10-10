"""路由注册入口：把各路由模块挂到路由表上。"""
from __future__ import annotations

from ..http import Router
from . import candidates, documents, system, tasks


def register(router: Router) -> None:
    system.register(router)
    documents.register(router)
    tasks.register(router)
    candidates.register(router)
