@file:Suppress("FunctionNaming", "MagicNumber", "ModifierMissing")

package com.hexteam.neurostenographer.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.hexteam.neurostenographer.ui.screens.HomeScreen
import com.hexteam.neurostenographer.ui.screens.LibraryScreen
import com.hexteam.neurostenographer.ui.screens.SettingsScreen
import com.hexteam.neurostenographer.ui.screens.TranscriptActions
import com.hexteam.neurostenographer.ui.screens.TranscriptScreen
import com.hexteam.neurostenographer.ui.viewmodel.MainViewModel

private data class NavItem(
    val route: String,
    val label: String,
    val icon: ImageVector,
)

private val navigationItems =
    listOf(
        NavItem("home", "Главная", Icons.Default.Home),
        NavItem("library", "Записи", Icons.Default.Folder),
        NavItem("settings", "Настройки", Icons.Default.Settings),
    )

@Composable
fun App(vm: MainViewModel) {
    val nav = rememberNavController()
    val state by vm.state.collectAsStateWithLifecycle()
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                val route = nav.currentBackStackEntryAsState().value?.destination?.route
                for (item in navigationItems) {
                    NavigationBarItem(
                        selected = route == item.route,
                        onClick = { nav.navigate(item.route) { launchSingleTop = true } },
                        icon = { Icon(item.icon, null) },
                        label = { Text(item.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = "home",
            modifier = Modifier.padding(padding),
        ) {
            composable("home") {
                HomeScreen(
                    state = state,
                    onImport = { uri, name -> vm.process(uri, name) },
                    onOpen = { nav.navigate("transcript/${it.id}") },
                    onCancel = vm::cancel,
                    onDismissError = vm::clearError,
                )
            }
            composable("library") {
                LibraryScreen(state.transcripts) { nav.navigate("transcript/${it.id}") }
            }
            composable("settings") { SettingsScreen(state) }
            composable("transcript/{id}") { entry ->
                val transcript = state.transcripts.firstOrNull { it.id == entry.arguments?.getString("id") }
                if (transcript != null) {
                    TranscriptScreen(
                        state = state,
                        transcript = transcript,
                        actions =
                            TranscriptActions(
                                onBack = { nav.popBackStack() },
                                onSummarize = { vm.summarize(it) },
                                onDismissSummary = vm::dismissSummary,
                            ),
                        jsonFor = { vm.json(it) },
                    )
                }
            }
        }
    }
}
