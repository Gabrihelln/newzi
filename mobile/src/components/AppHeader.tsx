import React from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';
import { firebaseAuth } from '../services/firebaseAuth';
import { useStyles } from '../theme';
import { useLogo } from './brand';
import { ProfileAvatar } from './SettingsKit';

/** Horizontal gutter of the four tab screens, so the header (and the content under it) sits in the same place on each. */
export const TAB_GUTTER = 18;

/**
 * The one header of Início, Explorar, Salvos and Perfil: the logo and the person's photo (or initials), at the
 * same size and position on every tab, so switching tabs never makes it jump. Search lives only in Explorar's field.
 */
export function AppHeader({ onAvatar }: { onAvatar: () => void }) {
  const s = useStyles(makeStyles);
  const user = firebaseAuth.currentUser;
  return <View style={s.header}>
    <Image source={useLogo()} resizeMode="contain" accessibilityLabel="NEWZI" style={s.logo} />
    <Pressable accessibilityRole="button" accessibilityLabel="Abrir dados pessoais" onPress={onAvatar} hitSlop={6}>
      <ProfileAvatar name={user?.displayName || user?.email || 'Newzi'} photo={user?.photoURL} size={42} letters={2} />
    </Pressable>
  </View>;
}

const makeStyles = () => StyleSheet.create({
  header: { height: 56, marginTop: 4, marginBottom: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  logo: { width: 126, height: 46, marginLeft: -3 },
});
