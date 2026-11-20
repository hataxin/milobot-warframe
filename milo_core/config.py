"""Typed Milo bot configuration, with the required versioned plugin section."""

from typing import ClassVar, Literal

from maibot_sdk import Field, PluginConfigBase


class PluginSection(PluginConfigBase):
    """Plugin configuration schema version."""

    __ui_label__: ClassVar[str] = "插件版本"
    __ui_icon__: ClassVar[str] = "info"
    __ui_order__: ClassVar[int] = 99

    config_version: str = Field(default="0.1.0", description="配置结构版本")


class MiloConfig(PluginConfigBase):
    """Settings generated and maintained by the Milo bot Runner."""

    __ui_label__: ClassVar[str] = "Warframe 助手设置"
    __ui_icon__: ClassVar[str] = "settings"
    __ui_order__: ClassVar[int] = 1

    plugin: PluginSection = Field(default_factory=PluginSection)
    enabled: bool = Field(
        default=True,
        description="启用 Warframe 查询",
        json_schema_extra={"group": "basic"},
    )
    output_mode: Literal["image", "text"] = Field(
        default="image",
        description="回复形式",
        json_schema_extra={"group": "render"},
    )
    font_path: str = Field(
        default="",
        description="中文字体文件路径；留空使用随插件附带的 MiSans",
        json_schema_extra={
            "placeholder": "留空默认使用随包 MiSans 字体",
            "group": "render",
        },
    )
    timeout_seconds: float = Field(
        default=10.0,
        ge=3,
        le=20,
        description="单次数据源请求超时秒数",
        json_schema_extra={"placeholder": "3 ~ 20（秒）", "group": "network"},
    )
    proxy_url: str = Field(
        default="",
        description="可选 HTTP/HTTPS 代理地址（如 http://127.0.0.1:7890；留空使用系统/环境代理）",
        json_schema_extra={"placeholder": "http://127.0.0.1:7890", "group": "network"},
    )
    subscription_enabled: bool = Field(
        default=True,
        description="启用后台订阅轮询推送",
        json_schema_extra={"group": "subscription"},
    )
    subscription_interval_seconds: int = Field(
        default=120,
        ge=60,
        le=3600,
        description="订阅轮询间隔秒数（最低 60 秒）",
        json_schema_extra={"placeholder": "60 ~ 3600（秒）", "group": "subscription"},
    )
