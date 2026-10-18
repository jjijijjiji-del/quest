package com.cury.listenmoney;

import android.Manifest;
import android.content.Intent;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.util.ArrayList;

/**
 * 말한 금액을 받아 적는 음성 인식.
 * 실어증 환자는 말하는 중간에 쉬는 경우가 많아서, 말이 끝났다고 판단하는 침묵 시간을 길게 잡는다.
 */
@CapacitorPlugin(
    name = "SpeechInput",
    permissions = { @Permission(strings = { Manifest.permission.RECORD_AUDIO }, alias = "mic") }
)
public class SpeechInputPlugin extends Plugin {

    private SpeechRecognizer recognizer;
    private PluginCall pending;
    private long lastLevelAt = 0;

    @PluginMethod
    public void available(PluginCall call) {
        JSObject r = new JSObject();
        r.put("available", SpeechRecognizer.isRecognitionAvailable(getContext()));
        call.resolve(r);
    }

    @PluginMethod
    public void listen(PluginCall call) {
        if (getPermissionState("mic") != PermissionState.GRANTED) {
            requestPermissionForAlias("mic", call, "micPermissionCallback");
            return;
        }
        startListening(call);
    }

    @PermissionCallback
    private void micPermissionCallback(PluginCall call) {
        if (getPermissionState("mic") == PermissionState.GRANTED) {
            startListening(call);
        } else {
            JSObject r = new JSObject();
            r.put("matches", new JSArray());
            r.put("error", 9);
            call.resolve(r);
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (recognizer != null) {
                try { recognizer.stopListening(); } catch (Exception ignored) {}
            }
        });
        call.resolve();
    }

    private void finish(ArrayList<String> matches, int error) {
        PluginCall call = pending;
        pending = null;
        if (call != null) {
            JSArray arr = new JSArray();
            if (matches != null) {
                for (String m : matches) arr.put(m);
            }
            JSObject r = new JSObject();
            r.put("matches", arr);
            r.put("error", error);
            call.resolve(r);
        }
        getActivity().runOnUiThread(this::destroyRecognizer);
    }

    private void destroyRecognizer() {
        if (recognizer != null) {
            try { recognizer.cancel(); } catch (Exception ignored) {}
            try { recognizer.destroy(); } catch (Exception ignored) {}
            recognizer = null;
        }
    }

    private void startListening(PluginCall call) {
        final long silenceMs = call.getInt("silenceMs", 3000).longValue();
        getActivity().runOnUiThread(() -> {
            if (pending != null) {
                finish(null, 8);
            }
            destroyRecognizer();
            if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
                JSObject r = new JSObject();
                r.put("matches", new JSArray());
                r.put("error", 100);
                call.resolve(r);
                return;
            }
            pending = call;
            recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) { state("ready"); }
                @Override public void onBeginningOfSpeech() { state("speaking"); }
                @Override public void onRmsChanged(float rmsdB) {
                    long now = System.currentTimeMillis();
                    if (now - lastLevelAt < 80) return;
                    lastLevelAt = now;
                    JSObject d = new JSObject();
                    d.put("level", rmsdB);
                    notifyListeners("level", d);
                }
                @Override public void onBufferReceived(byte[] buffer) {}
                @Override public void onEndOfSpeech() { state("thinking"); }
                @Override public void onError(int error) {
                    finish(null, error);
                }
                @Override public void onResults(Bundle results) {
                    ArrayList<String> m = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    finish(m, 0);
                }
                @Override public void onPartialResults(Bundle partial) {
                    ArrayList<String> m = partial.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (m != null && !m.isEmpty()) {
                        JSObject d = new JSObject();
                        d.put("text", m.get(0));
                        notifyListeners("partial", d);
                    }
                }
                @Override public void onEvent(int eventType, Bundle params) {}
            });

            Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR");
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ko-KR");
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5);
            intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            intent.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getContext().getPackageName());
            intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, silenceMs);
            intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, silenceMs);
            intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1500L);
            try {
                recognizer.startListening(intent);
            } catch (Exception e) {
                finish(null, 5);
            }
        });
    }

    private void state(String s) {
        JSObject d = new JSObject();
        d.put("state", s);
        notifyListeners("state", d);
    }

    @Override
    protected void handleOnDestroy() {
        destroyRecognizer();
        super.handleOnDestroy();
    }
}
