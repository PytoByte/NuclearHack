@file:Suppress("FunctionNaming", "MagicNumber", "ModifierMissing")

package com.hexteam.neurostenographer.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hexteam.neurostenographer.ui.viewmodel.MainState

@Composable
fun SettingsScreen(state: MainState) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Spacer(Modifier.height(24.dp))
        Text("Настройки", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(20.dp))
        SettingRow(
            title = "Обработка на устройстве",
            subtitle = "Аудио не покидает телефон, сеть не используется",
            checked = true,
        )
        SettingRow(
            title = "Определение говорящих",
            subtitle = "Автоматическая диаризация включена в конвейер",
            checked = true,
        )
        val summarySubtitle =
            if (state.summaryAvailable) {
                "Qwen3-0.6B доступна на устройстве"
            } else {
                "Модель Qwen не включена в эту сборку"
            }
        SettingRow(
            title = "Локальное резюме",
            subtitle = summarySubtitle,
            checked = state.summaryAvailable,
        )
        Spacer(Modifier.height(18.dp))
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(16.dp)) {
                Text("Конвейер", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(
                    "GigaAM-v3 CTC → диаризация → реплики с таймкодами. " +
                        "Текст и JSON формируются локальным C++ SDK.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(Modifier.padding(16.dp)) {
                Text("Приватность", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(
                    "Приложение не запрашивает INTERNET. Модели и аудио хранятся в приватном каталоге приложения.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SettingRow(
    title: String,
    subtitle: String,
    checked: Boolean,
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
        Switch(checked = checked, onCheckedChange = null)
    }
}
