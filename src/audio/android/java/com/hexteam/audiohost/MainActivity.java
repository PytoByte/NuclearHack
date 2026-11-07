package com.hexteam.audiohost;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONArray;
import org.json.JSONObject;

/** Minimal manual/offline SDK host, without a separate product UI stack. */
public final class MainActivity extends Activity {
    private TextView text;
    private Button export, summary;
    private File imported, result;
    private void persist() {
        getPreferences(MODE_PRIVATE).edit().putString("imported",imported==null?null:imported.toString())
            .putString("result",result==null?null:result.toString()).apply();
    }
    private final AtomicBoolean busy = new AtomicBoolean(false), cancel = new AtomicBoolean(false);
    private static void copy(InputStream input, OutputStream output) throws Exception {
        byte[] buffer = new byte[65536]; int n;
        while ((n = input.read(buffer)) >= 0) output.write(buffer, 0, n);
    }
    private void message(String value) { runOnUiThread(() -> text.setText(value)); }
    public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout column = new LinearLayout(this); column.setOrientation(LinearLayout.VERTICAL); column.setPadding(16, 80, 16, 32);
        Button open = new Button(this); open.setText("Импорт MP3"); column.addView(open);
        Button process = new Button(this); process.setText("Обработать локально"); column.addView(process);
        export = new Button(this); export.setText("Экспорт JSON"); export.setEnabled(false); column.addView(export);
        summary = new Button(this); summary.setText("Отдельное резюме"); summary.setEnabled(false); column.addView(summary);
        Button stop = new Button(this); stop.setText("Отмена"); column.addView(stop);
        ScrollView scroll = new ScrollView(this); text = new TextView(this);
        text.setText("Импортируйте локальный MP3. Обработка выполняется на устройстве.");
        scroll.addView(text); column.addView(scroll); setContentView(column);
        String previousInput=getPreferences(MODE_PRIVATE).getString("imported",null);
        String previousResult=getPreferences(MODE_PRIVATE).getString("result",null);
        if(previousInput!=null && new File(previousInput).isFile())imported=new File(previousInput);
        if(previousResult!=null && new File(previousResult).isFile())result=new File(previousResult);
        export.setEnabled(result!=null);summary.setEnabled(result!=null);
        if(imported!=null)text.setText("Импортированный MP3 сохранён. Можно повторить обработку с последнего завершённого чанка.");
        open.setOnClickListener(v -> {
            if (!busy.get()) startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE).setType("audio/mpeg"), 1);
        });
        process.setOnClickListener(v -> run(false));
        summary.setOnClickListener(v -> run(true));
        stop.setOnClickListener(v -> { cancel.set(true); message("Отмена запрошена; текущий шаг завершается."); });
        export.setOnClickListener(v -> {
            if (result != null && !busy.get()) startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE).setType("application/json")
                .putExtra(Intent.EXTRA_TITLE, "transcript.json"), 2);
        });
    }
    private void run(boolean summarize) {
        if ((summarize ? result == null : imported == null) || !busy.compareAndSet(false, true)) return;
        cancel.set(false); export.setEnabled(false); summary.setEnabled(false);
        if(!summarize){result=null;persist();}
        new Thread(() -> {
            try {
                File base = getFilesDir(), models = new File(base, "models");
                File output = new File(base, "result-" + System.currentTimeMillis() + (summarize ? ".txt" : ".json"));
                Native.listener = (stage, done, total) -> {
                    if (!stage.equals("decode") || done % 160000 == 0)
                        message(stage.startsWith("llm") ? "Формируется локальное резюме…" :
                            stage.startsWith("diarization") ? "Определяются говорящие…" :
                            stage.startsWith("asr") ? "Распознаётся речь…" : "Обработка…");
                    return cancel.get();
                };
                Native.JobOptions options=new Native.JobOptions();
                File checkpoint=new File(base,"job-cache/manual");
                if(!checkpoint.exists() && !checkpoint.mkdirs())throw new IllegalStateException("Cannot create checkpoint directory");
                options.checkpointDirectory=checkpoint.toString();
                int status = summarize ? Native.summarize(result.toString(),
                    new File(models, "qwen3-0.6b-q8/Qwen3-0.6B-Q8_0.gguf").toString(), output.toString(), 4) :
                    Native.transcribeJob(imported.toString(), output.toString(), models.toString(), base.toString(), options);
                if (status != 0) throw new IllegalStateException(status == 4 ? "Обработка отменена" : Native.lastError());
                if (summarize) message(new String(Files.readAllBytes(output.toPath()), StandardCharsets.UTF_8));
                else {
                    result = output;
                    persist();
                    JSONArray turns = new JSONObject(new String(Files.readAllBytes(output.toPath()), StandardCharsets.UTF_8)).getJSONArray("transcript");
                    StringBuilder view = new StringBuilder();
                    for (int i = 0; i < turns.length(); ++i) {
                        JSONObject t = turns.getJSONObject(i);
                        view.append(t.getString("speaker_id")).append(" ").append(t.getLong("start_ms"))
                            .append("–").append(t.getLong("end_ms")).append(" мс\n").append(t.getString("text")).append("\n\n");
                    }
                    message(view.length() > 0 ? view.toString() : "Речь не распознана.");
                }
            } catch (Throwable error) { message(error.toString()); }
            finally {
                Native.listener = null; busy.set(false);
                runOnUiThread(() -> { export.setEnabled(result != null); summary.setEnabled(result != null); });
            }
        }, "audio-sdk").start();
    }
    protected void onActivityResult(int request, int code, Intent data) {
        super.onActivityResult(request, code, data);
        if (code != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if(!busy.compareAndSet(false,true))return;
        new Thread(() -> {
            try {
                if (request == 1) {
                    File target = new File(getFilesDir(), "import-" + System.currentTimeMillis() + ".mp3");
                    try (InputStream in = getContentResolver().openInputStream(uri); OutputStream out = new FileOutputStream(target)) { copy(in, out); }
                    imported = target;result=null;persist();message("MP3 импортирован. Можно запускать обработку.");
                } else if (request == 2 && result != null) {
                    try (InputStream in = new FileInputStream(result); OutputStream out = getContentResolver().openOutputStream(uri)) { copy(in, out); }
                    message("JSON экспортирован.");
                }
            } catch (Throwable error) { message(error.toString()); }
            finally {busy.set(false);runOnUiThread(() -> {export.setEnabled(result!=null);summary.setEnabled(result!=null);});}
        }, "audio-file").start();
    }
}
