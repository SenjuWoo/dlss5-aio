@echo off
rem Launch a 32-bit Vulkan game (DXVK) with VK_LAYER_feed_vk active, without touching
rem the registry. The 32-bit sibling of ..\run-with-feed-layer.bat.
rem
rem   run-with-feed-layer32.bat "E:\path\to\game.exe" [args...]
rem
rem Only needed when dlss5-feed.log says the Vulkan interop entry points are missing --
rem i.e. DXVK resolved vkCreateDevice some way the add-on's in-process hook does not
rem intercept. VK_LAYER_PATH points at THIS directory, not the parent: the loader tries
rem every manifest it finds there, and the parent's is the 64-bit one.

setlocal
if "%~1"=="" (
    echo Usage: run-with-feed-layer32.bat "path\to\game.exe" [args...]
    exit /b 1
)
set "VK_LAYER_PATH=%~dp0"
set "VK_INSTANCE_LAYERS=VK_LAYER_feed_vk"
echo Launching with the 32-bit VK_LAYER_feed_vk from "%VK_LAYER_PATH%"
start "" %*
endlocal
