package com.hexteam.audiohost;

import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.json.JSONArray;
import org.json.JSONObject;

/** Evaluation host: input audio only; references/scoring remain off-device. */
public final class AsrInstrumentation extends Instrumentation {
    private Bundle arguments;
    public void onCreate(Bundle args) { super.onCreate(args); arguments=args; start(); }
    public void onStart() {
        Bundle status=new Bundle(); long handle=0;
        AtomicBoolean sampling=new AtomicBoolean(true); AtomicLong peak=new AtomicLong(0);
        Thread monitor=new Thread(() -> { while(sampling.get()) { peak.accumulateAndGet(Debug.getPss(),Math::max); SystemClock.sleep(100); } });
        try {
            String id=arguments.getString("run_id");
            if(id==null || !id.matches("exp_[0-9]+")) throw new IllegalArgumentException("Invalid run ID");
            File base=getTargetContext().getFilesDir(), run=new File(base,"results/"+id);
            if(run.exists() || !run.mkdirs()) throw new IllegalStateException("Output already exists/unavailable");
            String model=arguments.getString("model");
            if(model==null || !model.matches("[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("Invalid model ID");
            int threads=Integer.parseInt(arguments.getString("threads","4"));
            String modelFile=arguments.getString("model_file","model.int8.onnx");
            if(!modelFile.matches("[a-zA-Z0-9_.-]+")) throw new IllegalArgumentException("Invalid model filename");
            monitor.start(); long began=SystemClock.elapsedRealtime();
            handle=Native.asrCreate(new File(base,"models/"+model).toString(),arguments.getString("family"),modelFile,threads,
                arguments.getString("method","greedy_search"),arguments.getString("language","ru"),null);
            if(handle==0) throw new IllegalStateException(Native.lastError());
            long load=SystemClock.elapsedRealtime()-began;
            JSONArray inputs=new JSONArray(new String(Files.readAllBytes(new File(base,"fleurs-inputs.json").toPath()),StandardCharsets.UTF_8));
            JSONArray rows=new JSONArray(); long total=0;
            try(FileWriter output=new FileWriter(new File(run,"results.jsonl"))) {
                for(int i=0;i<inputs.length();++i) {
                    String audioId=inputs.getString(i);
                    if(!audioId.matches("[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("Invalid audio ID");
                    long start=SystemClock.elapsedRealtime();
                    String value=Native.asrDecode(handle,new File(base,"audio/fleurs/"+audioId+".wav").toString());
                    if(value==null) throw new IllegalStateException(Native.lastError());
                    long elapsed=SystemClock.elapsedRealtime()-start; total+=elapsed;
                    JSONObject row=new JSONObject().put("audio_id",audioId).put("backend",new JSONObject(value))
                        .put("decode_inference_ms",elapsed).put("model_instance_first_call",i==0);
                    rows.put(row);output.write(row.toString()+"\n");output.flush();
                    Bundle progress=new Bundle();progress.putInt("completed",i+1);sendStatus(0,progress);
                }
            }
            Native.asrDestroy(handle);handle=0;
            sampling.set(false);monitor.join();
            JSONObject metrics=new JSONObject().put("run_id",id).put("load_ms",load).put("decode_inference_ms",total)
                .put("sampled_peak_pss_kib",peak.get()).put("process_lifetime_peak_rss_kib",Native.peakRssKib())
                .put("pss_sample_period_ms",100).put("clips",rows.length()).put("rows",rows);
            try(FileWriter out=new FileWriter(new File(run,"metrics.json"))) {out.write(metrics.toString(2));}
            status.putString("result","PASS");finish(-1,status);
        } catch(Throwable error) {status.putString("result","FAIL");status.putString("error",error.toString());finish(0,status);}
        finally {sampling.set(false);if(handle!=0)Native.asrDestroy(handle);}
    }
}
