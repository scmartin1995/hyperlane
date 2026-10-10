"""API routers are auto-discovered: every module in this package exposing `router` is mounted under /api."""

from __future__ import annotations

import importlib
import logging
import pkgutil

from fastapi import APIRouter

log = logging.getLogger(__name__)


def collect_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)
        else:
            log.debug("api module %s has no router", mod.name)
    return routers
