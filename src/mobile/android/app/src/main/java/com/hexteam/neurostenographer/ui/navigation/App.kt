package com.hexteam.neurostenographer.ui.navigation

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.ui.viewmodel.MainViewModel
import com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage

private data class NavItem(val route: String, val label: String, val icon: ImageVector)

@Composable fun App(vm: MainViewModel) {
    val nav = rememberNavController()
    val state by vm.state.collectAsStateWithLifecycle()
    val items =
        listOf(
            NavItem("home", "Главная", Icons.Default.Home),
            NavItem("library", "Записи", Icons.Default.Folder),
            NavItem("settings", "Настройки", Icons.Default.Settings),
        )
    Scaffold(containerColor = MaterialTheme.colorScheme.background, bottomBar = {
        NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
            val route = nav.currentBackStackEntryAsState().value?.destination?.route
            items.forEach {
                NavigationBarItem(selected = route == it.route, onClick = {
                    nav.navigate(it.route) { launchSingleTop = true }
                }, icon = { Icon(it.icon, null) }, label = { Text(it.label) })
            }
        }
    }) { pad ->
        NavHost(navController = nav, startDestination = "home", modifier = Modifier.padding(pad)) {
            composable("home") {
                HomeScreen(state.transcripts.firstOrNull(), state.processing, state.progress, vm) {
                    nav.navigate("transcript/${it.id}")
                }
            }
            composable("library") { LibraryScreen(state.transcripts, vm) { nav.navigate("transcript/${it.id}") } }
            composable("settings") { SettingsScreen(state.settings, vm) }
            composable("transcript/{id}") { back ->
                val t = state.transcripts.firstOrNull { it.id == back.arguments?.getString("id") }
                if (t != null) TranscriptScreen(t, vm) { nav.popBackStack() }
            }
        }
    }
}

@Composable private fun HomeScreen(
    latest: Transcript?,
    processing: ProcessingStage,
    progress: Int,
    vm: MainViewModel,
    open: (Transcript) -> Unit,
) {
    val context = LocalContext.current
    val filePicker =
        rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
            uri?.let {
                vm.addFile(vmJsonName(context, it))
                vm.process(vmJsonName(context, it))
            }
        }
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
        Spacer(Modifier.height(24.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.AutoAwesome, null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(10.dp))
            Text("Neurostenographer", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(28.dp))
        Text("Новый материал", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(18.dp))
        Card(
            onClick = {
                filePicker.launch(arrayOf("audio/*"))
            },
            colors =
                CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                ),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(Modifier.padding(22.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(54.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary),
                    Alignment.Center,
                ) {
                    Icon(Icons.Default.FileUpload, null, tint = MaterialTheme.colorScheme.onPrimary)
                }
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text("Импорт аудио", fontWeight = FontWeight.Bold)
                    Text("MP3, M4A, WAV", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(Icons.Default.ChevronRight, null)
            }
        }
        Spacer(Modifier.height(12.dp))
        Card(
            onClick = {
                vm.process("Новая запись")
            },
            colors =
                CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(Modifier.padding(22.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(
                        54.dp,
                    ).clip(CircleShape).background(MaterialTheme.colorScheme.secondary.copy(alpha = .18f)),
                    Alignment.Center,
                ) {
                    Icon(Icons.Default.Mic, null, tint = MaterialTheme.colorScheme.secondary)
                }
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text("Записать разговор", fontWeight = FontWeight.Bold)
                    Text("Режим real-time доступен", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Icon(Icons.Default.ChevronRight, null)
            }
        }
        Spacer(Modifier.height(28.dp))
        Text("Недавняя расшифровка", fontWeight = FontWeight.Bold)
        if (processing != ProcessingStage.Idle) {
            ProcessingCard(processing, progress)
        } else {
            latest?.let {
                Spacer(Modifier.height(12.dp))
                TranscriptCard(it) { open(it) }
            }
        }
    }
}

private fun vmJsonName(
    context: android.content.Context,
    uri: Uri,
): String =
    context.contentResolver.query(uri, null, null, null, null)?.use { c ->
        val i = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
        if (i >= 0 && c.moveToFirst()) c.getString(i) else "audio.mp3"
    } ?: "audio.mp3"

@Composable private fun ProcessingCard(
    stage: ProcessingStage,
    progress: Int,
) {
    Card(
        Modifier.fillMaxWidth().padding(top = 12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(Modifier.padding(18.dp)) {
            val label =
                when (stage) {
                    ProcessingStage.Decoding -> "Анализ аудио"
                    ProcessingStage.Transcribing -> "Распознавание речи"
                    ProcessingStage.Separating -> "Определение говорящих"
                    else -> "Готово"
                }
            Text(label, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            LinearProgressIndicator(
                progress = progress / 100f,
                modifier = Modifier.fillMaxWidth(),
                trackColor = MaterialTheme.colorScheme.surfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Text("$progress%", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable private fun LibraryScreen(
    items: List<Transcript>,
    vm: MainViewModel,
    open: (Transcript) -> Unit,
) {
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp)) {
        Spacer(Modifier.height(24.dp))
        Text("Мои записи", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(18.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(items, key = { it.id }) {
                TranscriptCard(it) {
                    vm.select(it)
                    open(it)
                }
            }
        }
    }
}

@Composable private fun TranscriptCard(
    t: Transcript,
    onClick: () -> Unit,
) {
    Card(onClick = onClick, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(
                    46.dp,
                ).clip(RoundedCornerShape(12.dp)).background(MaterialTheme.colorScheme.primaryContainer),
                Alignment.Center,
            ) {
                Icon(Icons.Default.GraphicEq, null, tint = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(t.title, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    t.createdAt + "  •  " + t.utterances.size + " реплик",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Icon(Icons.Default.ChevronRight, null)
        }
    }
}

@Composable private fun SettingsScreen(
    settings: com.hexteam.neurostenographer.data.model.AppSettings,
    vm: MainViewModel,
) {
    var dense by remember { mutableStateOf(settings) }
    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Spacer(Modifier.height(24.dp))
        Text("Настройки", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(20.dp))
        SettingSwitch("Определение говорящих", "Разделять реплики автоматически", dense.speakerDetection) {
            dense = dense.copy(speakerDetection = it)
            vm.updateSettings(dense)
        }
        SettingSwitch("Сохранять слова-паразиты", "Не удалять «ээ», паузы и повторения", dense.preserveFillers) {
            dense = dense.copy(preserveFillers = it)
            vm.updateSettings(dense)
        }
        SettingSwitch("Режим real-time", "Расшифровка во время записи", dense.realtimeMode) {
            dense = dense.copy(realtimeMode = it)
            vm.updateSettings(dense)
        }
        Spacer(Modifier.height(18.dp))
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(16.dp)) {
                Text("Приватность", fontWeight = FontWeight.Bold)
                Text(
                    "Вся обработка выполняется локально. Приложение не запрашивает интернет.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable private fun SettingSwitch(
    title: String,
    subtitle: String,
    checked: Boolean,
    onChecked: (Boolean) -> Unit,
) {
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Switch(checked = checked, onCheckedChange = onChecked)
    }
}

@Composable private fun TranscriptScreen(
    t: Transcript,
    vm: MainViewModel,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val export =
        rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
            uri?.let {
                context.contentResolver.openOutputStream(it)?.use {
                        s ->
                    s.write(vm.json(t).toByteArray())
                }
            }
        }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, null) }
            Text(
                t.title,
                Modifier.weight(1f),
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            IconButton(onClick = { export.launch(t.title + ".json") }) { Icon(Icons.Default.FileDownload, null) }
        }
        LazyColumn(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(t.utterances) { u ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(16.dp)) {
                        Row(Modifier.fillMaxWidth()) {
                            AssistChip(
                                onClick = {},
                                label = { Text(if (u.speakerId.endsWith("1")) "Спикер 1" else "Спикер 2") },
                            )
                            Spacer(Modifier.weight(1f))
                            Text(
                                formatTime(u.startMs),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(u.text)
                    }
                }
            }
        }
    }
}

private fun formatTime(ms: Long): String {
    val s = ms / 1000
    return "%02d:%02d".format(s / 60, s % 60)
}
