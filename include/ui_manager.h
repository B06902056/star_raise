#ifndef UI_MANAGER_H
#define UI_MANAGER_H

#include "raylib.h"

#define SCREEN_WIDTH 2556
#define SCREEN_HEIGHT 1179
#define SAFE_MARGIN_X 132
#define BOTTOM_MARGIN_Y 63

void InitGameUI(void);
void UpdateGameUI(int *minerals, float *incomeTimer);
void DrawGameUI(int minerals, float incomeTimer);
void UnloadGameUI(void);

#endif
