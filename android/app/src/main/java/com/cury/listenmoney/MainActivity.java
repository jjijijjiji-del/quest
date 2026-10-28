package com.cury.listenmoney;

import android.os.Bundle;
import android.view.View;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(SpeechInputPlugin.class);
        registerPlugin(RawRecorderPlugin.class);
        super.onCreate(savedInstanceState);
        // 화면 끝에서 당겼을 때 늘어나는 효과와 오른쪽 스크롤 막대를 없앰 (문제 풀 때 화면이 움직이지 않게)
        WebView wv = getBridge().getWebView();
        wv.setOverScrollMode(View.OVER_SCROLL_NEVER);
        wv.setVerticalScrollBarEnabled(false);
        wv.setHorizontalScrollBarEnabled(false);
    }
}
