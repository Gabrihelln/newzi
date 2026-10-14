import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { getThemePreference, setThemePreference, type ThemePreference } from '../theme/appearance';
import { spacing, typography, useTheme } from '../theme';
import { Icon, type IconName } from './Icon';
import { BrandPage, BrandPageHeader, SettingsCard, SettingsSection } from './ScreenPrimitives';

const OPTIONS: { value: ThemePreference; title: string; description: string; icon: IconName }[] = [
  { value: 'system', title: 'Automático', description: 'Segue o tema do celular.', icon: 'settings' },
  { value: 'light', title: 'Claro', description: 'Fundo claro o tempo todo.', icon: 'sun' },
  { value: 'dark', title: 'Escuro', description: 'Fundo escuro, mais confortável à noite.', icon: 'moon' },
];

export function AppearanceScreen({ onBack }: { onBack: () => void }) {
  const { colors } = useTheme();
  const [preference, setPreference] = useState(getThemePreference);
  const choose = (value: ThemePreference) => { setPreference(value); setThemePreference(value); };
  return <BrandPage>
    <BrandPageHeader title="Aparência" subtitle="Escolha como o Newzi aparece neste aparelho." onBack={onBack} />
    <SettingsSection title="Tema">
      <SettingsCard>
        <View accessibilityRole="radiogroup">
          {OPTIONS.map((option, index) => {
            const selected = preference === option.value;
            return <Pressable key={option.value} accessibilityRole="radio" accessibilityState={{ checked: selected }} accessibilityLabel={`${option.title}. ${option.description}`}
              onPress={() => choose(option.value)}
              style={({ pressed }) => ({ minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.sm,
                borderTopWidth: index ? 1 : 0, borderColor: colors.divider, opacity: pressed ? .7 : 1 })}>
              <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceBlue, alignItems: 'center', justifyContent: 'center' }}>
                <Icon name={option.icon} color={colors.primary} size={20} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.textPrimary, fontFamily: typography.fontFamily.ui, fontWeight: '700', fontSize: 16 }}>{option.title}</Text>
                <Text style={{ color: colors.secondary, fontFamily: typography.fontFamily.ui, fontSize: 13, marginTop: 2 }}>{option.description}</Text>
              </View>
              <View style={{ width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: selected ? colors.primary : colors.muted, alignItems: 'center', justifyContent: 'center' }}>
                {selected && <View style={{ width: 11, height: 11, borderRadius: 6, backgroundColor: colors.primary }} />}
              </View>
            </Pressable>;
          })}
        </View>
      </SettingsCard>
    </SettingsSection>
  </BrandPage>;
}
