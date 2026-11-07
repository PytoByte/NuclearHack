import java.io.File

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val repoRoot = rootProject.projectDir.parentFile.parentFile.parentFile
val nativeAbis = listOf("arm64-v8a", "x86_64")
val generatedNativeDirectory = layout.buildDirectory.dir("generated/native-audio/jniLibs")
val generatedAssetsDirectory = layout.buildDirectory.dir("generated/native-audio/assets")
val requireNativeAudio = providers.gradleProperty("requireNativeAudio").isPresent

val syncNativeAudio by tasks.registering {
    inputs.files(
        fileTree(repoRoot.resolve(".build")) {
            include("android-*/libnuclear_audio.so", "android-*/libnuclear_audio_jni.so", "llama-android-*/bin/*.so")
        },
        fileTree(repoRoot.resolve(".tools/sherpa-android")) {
            include("*/libsherpa-onnx-c-api.so", "*/libonnxruntime.so")
        },
    )
    outputs.dir(generatedNativeDirectory)
    doLast {
        val destination = generatedNativeDirectory.get().asFile
        destination.deleteRecursively()
        var copied = 0
        for (abi in nativeAbis) {
            val sdkDirectory = repoRoot.resolve(".build/android-$abi")
            val sherpaDirectory = repoRoot.resolve(".tools/sherpa-android/$abi")
            val required =
                listOf(
                    sdkDirectory.resolve("libnuclear_audio.so"),
                    sdkDirectory.resolve("libnuclear_audio_jni.so"),
                    sherpaDirectory.resolve("libsherpa-onnx-c-api.so"),
                    sherpaDirectory.resolve("libonnxruntime.so"),
                )
            if (!required.all(File::isFile)) continue
            val libraries = required.toMutableList()
            val llamaDirectory = repoRoot.resolve(".build/llama-android-$abi/bin")
            if (llamaDirectory.isDirectory) {
                libraries += llamaDirectory.listFiles { file -> file.extension == "so" }.orEmpty()
            }
            val target = destination.resolve(abi).apply { mkdirs() }
            for (library in libraries) {
                library.copyTo(target.resolve(library.name), overwrite = true)
            }
            copied++
        }
        if (copied == 0) {
            logger.warn("Native audio libraries missing; run make mobile-build before packaging.")
            if (requireNativeAudio) {
                throw GradleException("Native audio libraries are required for this APK build.")
            }
        }
    }
}

val syncAudioAssets by tasks.registering {
    inputs.files(
        fileTree(repoRoot.resolve("models")) {
            include(
                "giga-v3-ctc/**",
                "giga-v3-ctc-punct/**",
                "diarization/**",
                "nemotron3-diarization/**",
                "qwen3-0.6b-q8/**",
            )
        },
    )
    outputs.dir(generatedAssetsDirectory)
    doLast {
        val destination = generatedAssetsDirectory.get().asFile
        destination.deleteRecursively()
        val modelRoot = repoRoot.resolve("models")
        val modelSets =
            listOf(
                "giga-v3-ctc",
                "giga-v3-ctc-punct",
                "diarization",
                "nemotron3-diarization",
                "qwen3-0.6b-q8",
            )
        var copied = 0
        for (name in modelSets) {
            val source = modelRoot.resolve(name)
            if (!source.isDirectory) continue
            source.copyRecursively(destination.resolve("models").resolve(name), overwrite = true)
            copied++
        }
        if (copied == 0) {
            logger.warn("Local models missing; run scripts/bootstrap_models.py before packaging.")
            if (requireNativeAudio) {
                throw GradleException("Local audio models are required for this APK build.")
            }
        }
    }
}

android {
    namespace = "com.hexteam.neurostenographer"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "com.hexteam.neurostenographer"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += listOf("onnx", "onnx_data", "gguf", "txt", "json") }
    packaging { jniLibs { useLegacyPackaging = true } }
    sourceSets["main"].jniLibs.srcDir(generatedNativeDirectory.get().asFile)
    sourceSets["main"].assets.srcDir(generatedAssetsDirectory.get().asFile)

    lint {
        abortOnError = true
        warningsAsErrors = true
        checkDependencies = true
        xmlReport = true
        htmlReport = true
        baseline = file("lint-baseline.xml")
    }
}

tasks.named("preBuild") { dependsOn(syncNativeAudio, syncAudioAssets) }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
