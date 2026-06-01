'use client';

import * as Lucide from 'lucide-react';
import type { ComponentType } from 'react';
import type { LucideProps } from 'lucide-react';

/**
 * 이름 기반 lucide 아이콘 래퍼.
 *
 * 시안(Flowit.html)이 아이콘을 `data-lucide="message-square"` 처럼 kebab-case
 * 문자열로 — 특히 마켓플레이스/노드 카드처럼 데이터에서 동적으로 — 참조하기 때문에,
 * 정적 import 대신 이름으로 부르는 래퍼를 둔다.
 *
 * 해석 순서: 정식 `icons` 레지스트리 → named export(구 이름 별칭 포함).
 * lucide v1에서 일부 아이콘이 리네임(alert-triangle→TriangleAlert 등)됐는데,
 * 구 PascalCase 이름이 named export 별칭으로 남아 있어 폴백으로 커버한다.
 *
 * 트레이드오프: 모듈 전체를 참조하므로 트리셰이킹이 약해진다. 사내 도구 수준에서는
 * 허용 가능하며, 추후 정적 아이콘은 직접 import로 최적화할 수 있다.
 */
export interface IconProps extends LucideProps {
  /** kebab-case lucide 아이콘 이름 (예: "message-square", "check-circle-2") */
  name: string;
}

function toPascalCase(name: string): string {
  return name
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');
}

const registry = Lucide.icons as Record<string, ComponentType<LucideProps>>;
const namespace = Lucide as unknown as Record<string, ComponentType<LucideProps>>;

export default function Icon({ name, ...props }: IconProps) {
  const key = toPascalCase(name);
  const LucideIcon = registry[key] ?? namespace[key];
  if (typeof LucideIcon !== 'object' && typeof LucideIcon !== 'function') {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn(`[Icon] 알 수 없는 lucide 아이콘: "${name}"`);
    }
    return null;
  }
  return <LucideIcon {...props} />;
}
