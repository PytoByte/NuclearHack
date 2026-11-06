package com.hexteam.neurostenographer

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.hexteam.neurostenographer.ui.navigation.App
import com.hexteam.neurostenographer.ui.theme.NeuroTheme
import com.hexteam.neurostenographer.ui.viewmodel.MainViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { NeuroTheme { App(viewModel<MainViewModel>()) } }
    }
}
