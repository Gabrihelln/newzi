import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Platform, StyleProp, View, ViewStyle } from 'react-native';
import { API_BASE_URL } from '../config/env';
import { getFirebaseIdToken } from '../services/firebaseAuth';
import { colors } from '../theme';
import { Icon } from './Icon';

type Props = { uri?: string | null; articleId?: string; style?: StyleProp<ViewStyle>; accessibilityLabel?: string };

export function isCanonicalArticleImageUrl(value?: string | null) {
  if (!value) return false;
  try {
    const url = new URL(value);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return false;
    const path = url.pathname.toLocaleLowerCase('en-US');
    if (path.endsWith('.avif') || path.includes('format(avif)')) return false;
    const parts = path.split('/').filter(Boolean);
    const file = parts[parts.length - 1] || '';
    const stem = file.replace(/\.[a-z0-9]+$/, '');
    if (parts.some(part => /^(favicon|favicons|logo|logos|branding|avatar|avatars|placeholder|mascot|category-image|category-photo|generic|default-images|random-images)$/.test(part))) return false;
    return !/^(new-(reading|waving|sunrise|celebrate)|mascot|article-fallback|category-(image|photo)(?:-[a-z0-9_-]+)?|generic|default-image|random)$/.test(stem)
      && !/(^|[/_-])(pixel|spacer|tracking)([._/?-]|$)/i.test(path);
  } catch {
    return false;
  }
}

function needsWebpProxy(value?: string | null) {
  if (!value) return false;
  const path = value.toLocaleLowerCase('en-US');
  return path.includes('.webp') || path.includes('format(webp)') || path.includes('format=webp');
}

type LoadState = { key: string; token: string | null; loaded: boolean; failed: boolean };

export function ArticleImage({ uri, articleId, style, accessibilityLabel = 'Imagem da notícia' }: Props) {
  const key = `${articleId || ''}|${uri || ''}`;
  const proxy = Platform.OS === 'ios' && needsWebpProxy(uri);
  const [state, setState] = useState<LoadState | null>(null);
  useEffect(() => {
    let active = true;
    setState({ key, token: null, loaded: false, failed: false });
    if (proxy) {
      if (!articleId) {
        setState({ key, token: null, loaded: false, failed: true });
        return () => { active = false; };
      }
      getFirebaseIdToken().then(token => {
        if (active) setState({ key, token, loaded: false, failed: !token });
      }).catch(() => {
        if (active) setState({ key, token: null, loaded: false, failed: true });
      });
    }
    return () => { active = false; };
  }, [key, proxy, articleId]);

  const current = state?.key === key ? state : null;
  const valid = isCanonicalArticleImageUrl(uri);
  const apiBase = API_BASE_URL.replace(/\/$/, '');
  const imageUri = proxy && articleId ? `${apiBase}/api/v1/articles/${encodeURIComponent(articleId)}/image` : uri;
  const showImage = valid && Boolean(imageUri) && Boolean(current) && !current?.failed && (!proxy || Boolean(current?.token));
  const loading = valid && !current?.failed && (!current?.loaded || !current);
  return <View accessible accessibilityLabel={accessibilityLabel} style={[{ overflow: 'hidden', backgroundColor: '#EAF3FB', alignItems: 'center', justifyContent: 'center' }, style]}>
    {showImage && imageUri
      ? <Image key={key} source={{ uri: imageUri, ...(current?.token ? { headers: { Authorization: `Bearer ${current.token}` } } : {}) }} onLoad={() => setState(value => value?.key === key ? { ...value, loaded: true } : value)} onError={() => setState(value => value?.key === key ? { ...value, failed: true } : value)} resizeMode="cover" accessibilityLabel={accessibilityLabel} style={{ position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, width: '100%', height: '100%' }} />
      : loading ? <ActivityIndicator accessibilityLabel="Carregando imagem da notícia" size="small" color={colors.secondary} /> : <Icon name="image" color={colors.secondary} size={24} />}
  </View>;
}
