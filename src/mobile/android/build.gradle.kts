import org.jlleitschuh.gradle.ktlint.KtlintExtension
import io.gitlab.arturbosch.detekt.extensions.DetektExtension

plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("org.jlleitschuh.gradle.ktlint") version "12.1.1" apply false
    id("io.gitlab.arturbosch.detekt") version "1.23.7" apply false
}

subprojects {
    apply(plugin = "org.jlleitschuh.gradle.ktlint")
    apply(plugin = "io.gitlab.arturbosch.detekt")

    configure<KtlintExtension> {
        android.set(true)
        ignoreFailures.set(false)
        filter {
            exclude("**/generated/**")
        }
    }

    configure<DetektExtension> {
        buildUponDefaultConfig = true
        allRules = true
        config.setFrom(files("$rootDir/config/detekt/detekt.yml"))
        parallel = true
        baseline = file("detekt-baseline.xml")
    }

    dependencies {
        "detektPlugins"("io.gitlab.arturbosch.detekt:detekt-formatting:1.23.7")
        "detektPlugins"("io.nlopez.compose.rules:detekt:0.4.16")
    }
}

tasks.register("installGitHooks") {
    group = "git hooks"
    description = "Installs repository Git hooks from scripts/."
    doLast {
        val fallbackRoot = rootProject.projectDir.parentFile.parentFile.parentFile
        val repoRootPath = try {
            val output = providers.exec {
                commandLine("git", "rev-parse", "--show-toplevel")
                isIgnoreExitValue = true
            }.standardOutput.asText.get().trim()
            if (output.isNotEmpty()) output else fallbackRoot.absolutePath
        } catch (e: Exception) {
            fallbackRoot.absolutePath
        }
        val repoRoot = file(repoRootPath)
        val hooksDir = repoRoot.resolve(".git/hooks").apply { mkdirs() }

        copy {
            from(repoRoot.resolve("scripts/pre-commit.sh"))
            into(hooksDir)
            rename { "pre-commit" }
            filePermissions { unix("rwxr-xr-x") }
        }
        copy {
            from(repoRoot.resolve("scripts/pre-push.sh"))
            into(hooksDir)
            rename { "pre-push" }
            filePermissions { unix("rwxr-xr-x") }
        }
    }
}
