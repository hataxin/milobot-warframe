"""Typed Milo bot configuration, with the required versioned plugin section."""

from typing import Literal

from maibot_sdk import Field, PluginConfigBase


class PluginSection(PluginConfigBase):
    """Plugin configuration schema version."""

    config_version: str = Field(default="0.1.0", description="配置结构版本")


class MiloConfig(PluginConfigBase):
    """Settings generated and maintained by the Milo bot Runner."""

    plugin: PluginSection = Field(default_factory=PluginSection)
    enabled: bool = Field(default=True, description="启用 Warframe 查询")
    output_mode: Literal["image", "text"] = Field(default="image", description="回复形式")
    font_path: str = Field(default="", description="中文字体文件路径；留空使用随插件附带的 MiSans")
    timeout_seconds: float = Field(default=10.0, ge=3, le=20, description="单次数据源请求超时秒数")
    subscription_enabled: bool = Field(default=True, description="启用后台订阅轮询推送")
    subscription_interval_seconds: int = Field(
        default=120,
        ge=60,
        le=3600,
        description="订阅轮询间隔秒数（最低 60 秒）",
    )
