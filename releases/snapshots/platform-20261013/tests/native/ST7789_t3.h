#pragma once
struct ST7789_t3 {
 template<class... T> ST7789_t3(T...){}
 template<class... T> void init(T...){}
 template<class... T> void setRotation(T...){}
 template<class... T> void fillScreen(T...){}
 template<class... T> void setTextSize(T...){}
 template<class... T> void setTextColor(T...){}
 template<class... T> void setCursor(T...){}
 template<class... T> void print(T...){}
 template<class... T> void drawChar(T...){}
};
