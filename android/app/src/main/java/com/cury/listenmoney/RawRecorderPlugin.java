package com.cury.listenmoney;

import android.Manifest;
import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Build;
import android.util.Base64;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.ByteArrayOutputStream;

/**
 * 보호자 목소리 녹음용 원음 녹음기.
 * 웹 화면의 마이크는 기기에 따라 통화용 처리(잡음 제거·대역 제한)가 붙어 먹먹해질 수 있어서,
 * 안드로이드 녹음기를 직접 써서 처리 없는 소리(UNPROCESSED, 안 되면 VOICE_RECOGNITION)를 48kHz로 받는다.
 */
@CapacitorPlugin(
    name = "RawRecorder",
    permissions = { @Permission(strings = { Manifest.permission.RECORD_AUDIO }, alias = "mic") }
)
public class RawRecorderPlugin extends Plugin {

    private AudioRecord rec;
    private Thread worker;
    private volatile boolean running = false;
    private ByteArrayOutputStream pcm;
    private int rate = 48000;
    private String sourceName = "";

    @PluginMethod
    public void start(PluginCall call) {
        if (getPermissionState("mic") != PermissionState.GRANTED) {
            requestPermissionForAlias("mic", call, "micCallback");
            return;
        }
        begin(call);
    }

    @PermissionCallback
    private void micCallback(PluginCall call) {
        if (getPermissionState("mic") == PermissionState.GRANTED) begin(call);
        else call.reject("mic");
    }

    private void begin(PluginCall call) {
        stopInternal();
        int[] rates = { 48000, 44100 };
        int[] sources;
        boolean unprocessed = false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            AudioManager am = (AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
            unprocessed = "true".equals(am.getProperty(AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED));
        }
        sources = unprocessed
            ? new int[] { MediaRecorder.AudioSource.UNPROCESSED, MediaRecorder.AudioSource.VOICE_RECOGNITION, MediaRecorder.AudioSource.MIC }
            : new int[] { MediaRecorder.AudioSource.VOICE_RECOGNITION, MediaRecorder.AudioSource.MIC };
        for (int src : sources) {
            for (int r : rates) {
                try {
                    int min = AudioRecord.getMinBufferSize(r, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                    if (min <= 0) continue;
                    AudioRecord a = new AudioRecord(src, r, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(min * 4, r));
                    if (a.getState() != AudioRecord.STATE_INITIALIZED) { a.release(); continue; }
                    rec = a;
                    rate = r;
                    sourceName = src == MediaRecorder.AudioSource.UNPROCESSED ? "unprocessed" : src == MediaRecorder.AudioSource.VOICE_RECOGNITION ? "voice_recognition" : "mic";
                    break;
                } catch (Exception ignored) {}
            }
            if (rec != null) break;
        }
        if (rec == null) { call.reject("init"); return; }
        pcm = new ByteArrayOutputStream();
        running = true;
        try { rec.startRecording(); } catch (Exception e) { stopInternal(); call.reject("start"); return; }
        final AudioRecord a = rec;
        worker = new Thread(() -> {
            byte[] buf = new byte[4096];
            while (running) {
                int n = a.read(buf, 0, buf.length);
                if (n > 0) synchronized (this) { pcm.write(buf, 0, n); }
            }
        });
        worker.start();
        JSObject r = new JSObject();
        r.put("sr", rate);
        r.put("source", sourceName);
        call.resolve(r);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        byte[] data;
        running = false;
        try { if (worker != null) worker.join(500); } catch (InterruptedException ignored) {}
        synchronized (this) { data = pcm == null ? new byte[0] : pcm.toByteArray(); }
        stopInternal();
        JSObject r = new JSObject();
        r.put("sr", rate);
        r.put("source", sourceName);
        r.put("data", Base64.encodeToString(data, Base64.NO_WRAP));
        call.resolve(r);
    }

    private void stopInternal() {
        running = false;
        if (rec != null) {
            try { rec.stop(); } catch (Exception ignored) {}
            try { rec.release(); } catch (Exception ignored) {}
            rec = null;
        }
        worker = null;
    }

    @Override
    protected void handleOnDestroy() { stopInternal(); }
}
