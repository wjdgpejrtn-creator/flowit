/**
 * 노드 타입 → lucide 아이콘 + 색 매핑.
 *
 * 시안(Flowit.html)의 iconMarkup() 포팅. 시안은 service 필드로 분기했으나,
 * 실제 카탈로그(NodeConfig)는 node_type / category 만 제공하므로 그 기준으로 해석한다.
 * 브랜드 컬러(슬랙·구글)는 시안 값을 그대로 쓰고, 나머지는 메인 액센트 갈색.
 */
export interface NodeIconSpec {
  /** kebab-case lucide 아이콘 이름 */
  icon: string;
  /** CSS color (토큰 var 또는 hex) */
  color: string;
}

const ACCENT = 'var(--color-accent)';

export function resolveNodeIcon(nodeType?: string, category?: string): NodeIconSpec {
  const t = (nodeType ?? '').toLowerCase();
  const c = (category ?? '').toLowerCase();

  if (t.includes('slack')) return { icon: 'message-square', color: '#4A154B' };
  if (t.includes('google') || t.includes('sheet') || t.includes('gsheet'))
    return { icon: 'sheet', color: '#0F9D58' };
  if (t.includes('gmail') || t.includes('email') || t.includes('mail'))
    return { icon: 'mail', color: ACCENT };
  if (t.includes('webhook')) return { icon: 'webhook', color: ACCENT };
  if (t.includes('notion')) return { icon: 'book-text', color: ACCENT };
  if (t.startsWith('it_ops') || t.includes('server') || t.includes('restart'))
    return { icon: 'server-cog', color: ACCENT };
  if (t.includes('template')) return { icon: 'type', color: ACCENT };
  if (t.includes('ecommerce') || c.includes('ecommerce'))
    return { icon: 'shopping-cart', color: ACCENT };
  if (t.includes('voc') || t.includes('customer') || t.includes('support'))
    return { icon: 'headphones', color: ACCENT };
  if (t.includes('pdf') || t.includes('parse') || t.includes('doc'))
    return { icon: 'file-text', color: ACCENT };
  if (c.includes('trigger') || t.includes('cron') || t.includes('schedule'))
    return { icon: 'clock', color: ACCENT };
  if (c.includes('ai') || t.includes('llm') || t.includes('agent'))
    return { icon: 'sparkles', color: ACCENT };

  return { icon: 'zap', color: ACCENT };
}
