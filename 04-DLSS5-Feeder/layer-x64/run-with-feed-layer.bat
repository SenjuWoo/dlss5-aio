@echo off
rem Launch a Vulkan game with VK_LAYER_feed_vk active, without touching the registry.
rem
rem   run-with-feed-layer.bat "E:\path\to\game.exe" [args...]
rem
rem Only needed when dlss5-feed.log says the Vulkan interop entry points are missing.
rem Registry implicit-layer keys are deliberately avoided: other hook software
rem (overlays, capture tools) rewrites them, and a per-launch env var cannot be
rem clobbered or leak into other games.

setlocal
if "%~1"=="" (
    echo Usage: run-with-feed-layer.bat "path\to\game.exe" [args...]
    exit /b 1
)
set "VK_LAYER_PATH=%~dp0"
set "VK_INSTANCE_LAYERS=VK_LAYER_feed_vk"
echo Launching with VK_LAYER_feed_vk from "%VK_LAYER_PATH%"
start "" %*
endlocal
