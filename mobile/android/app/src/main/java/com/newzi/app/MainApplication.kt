package com.newzi.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.facebook.react.PackageList
import com.facebook.react.ReactApplication
import com.facebook.react.ReactHost
import com.facebook.react.ReactNativeApplicationEntryPoint.loadReactNative
import com.facebook.react.defaults.DefaultReactHost.getDefaultReactHost

class MainApplication : Application(), ReactApplication {
  override val reactHost: ReactHost by lazy {
    getDefaultReactHost(
      context = applicationContext,
      packageList = PackageList(this).packages.apply {
        // Packages that cannot be autolinked yet can be added manually here.
        add(NewziAudioCachePackage())
      },
    )
  }

  override fun onCreate() {
    super.onCreate()
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val channel = NotificationChannel("daily_briefing", "Briefing diário", NotificationManager.IMPORTANCE_DEFAULT)
      getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }
    loadReactNative(this)
  }
}
