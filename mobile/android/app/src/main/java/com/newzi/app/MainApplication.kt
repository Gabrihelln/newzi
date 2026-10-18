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
      // One channel per push kind (the backend picks it), so each can be muted in Android settings.
      val manager = getSystemService(NotificationManager::class.java)
      // Creating an existing channel again only updates its name and description, never the user's choices.
      manager.createNotificationChannel(NotificationChannel("daily_briefing", "Resumo diário", NotificationManager.IMPORTANCE_DEFAULT).apply {
        description = "Avisa quando o seu resumo em áudio do dia fica pronto."
      })
      manager.createNotificationChannel(NotificationChannel("breaking_news", "Notícias urgentes", NotificationManager.IMPORTANCE_HIGH).apply {
        description = "Notícias importantes dos seus temas, com um resumo curto."
      })
      manager.createNotificationChannel(NotificationChannel("team_alerts", "Seu time", NotificationManager.IMPORTANCE_HIGH).apply {
        description = "Início dos jogos, gols, resultado final e notícias dos seus times."
      })
      manager.createNotificationChannel(NotificationChannel("announcements", "Novidades do Newzi", NotificationManager.IMPORTANCE_DEFAULT).apply {
        description = "Recursos novos e avisos importantes sobre o app."
      })
      manager.createNotificationChannel(NotificationChannel("promotions", "Ofertas e promoções", NotificationManager.IMPORTANCE_LOW).apply {
        description = "Descontos e ofertas do Newzi Premium."
      })
    }
    loadReactNative(this)
  }
}
