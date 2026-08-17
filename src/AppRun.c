#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>

int main(int argc, char *argv[]) {
    char *appdir = getenv("APPDIR");
    if (!appdir) appdir = ".";
    
    char path[4096];
    char lib_path[4096];
    
    snprintf(path, sizeof(path), "%s/usr/bin/pinginfo", appdir);
    snprintf(lib_path, sizeof(lib_path), "%s/usr/lib:%s/usr/bin/_internal", appdir, appdir);
    
    setenv("LD_LIBRARY_PATH", lib_path, 1);
    
    char *new_argv[argc + 1];
    new_argv[0] = path;
    for (int i = 1; i < argc; i++)
        new_argv[i] = argv[i];
    new_argv[argc] = NULL;
    
    execv(path, new_argv);
    perror("execv");
    return 1;
}
