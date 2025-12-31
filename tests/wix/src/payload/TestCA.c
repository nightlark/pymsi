// Tiny native DLL for MSI DLL custom action tests.
// Exports: DoNothing

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

// MSI custom action signature can be:
//   UINT __stdcall CA(MSIHANDLE hInstall);
// but for the purposes of tests we only need an exported function.

#ifdef __cplusplus
extern "C" {
#endif

__declspec(dllexport) UINT __stdcall DoNothing(void* hInstall)
{
    (void)hInstall;
    return 0; // ERROR_SUCCESS
}

#ifdef __cplusplus
}
#endif

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved)
{
    (void)hinstDLL;
    (void)fdwReason;
    (void)lpvReserved;
    return TRUE;
}
