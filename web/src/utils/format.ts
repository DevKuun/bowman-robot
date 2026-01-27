/**
 * Format utilities for the dashboard
 */

/**
 * Parse date string and ensure it's treated as UTC
 */
function parseAsUTC(date: Date | string): Date {
  if (typeof date === 'string') {
    // If no timezone indicator, assume UTC and add Z
    if (!date.endsWith('Z') && !date.includes('+') && !date.includes('-', 10)) {
      return new Date(date + 'Z');
    }
    return new Date(date);
  }
  return date;
}

/**
 * Format time only in KST (HH:MM:SS)
 */
export function formatTimeKST(date: Date | string): string {
  const d = parseAsUTC(date);
  return d.toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * Format date and time in KST (MM/DD HH:MM:SS)
 */
export function formatDateTimeKST(date: Date | string): string {
  const d = parseAsUTC(date);
  return d.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * Format full date and time in KST (YYYY. MM. DD. HH:MM:SS)
 */
export function formatFullDateTimeKST(date: Date | string): string {
  const d = parseAsUTC(date);
  return d.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * Format short time in KST (HH:MM)
 */
export function formatShortTimeKST(date: Date | string): string {
  const d = parseAsUTC(date);
  return d.toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/**
 * Format number with Korean locale
 */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return value.toLocaleString('ko-KR', options);
}

/**
 * Format currency (KRW or USDT)
 */
export function formatCurrency(value: number, currency: string = 'KRW'): string {
  if (currency === 'KRW') {
    return `${formatNumber(Math.round(value))} KRW`;
  }
  return `${formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

/**
 * Format percentage
 */
export function formatPercent(value: number, decimals: number = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
}

/**
 * Format duration in human readable format
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}초`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분`;
  
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}시간 ${minutes}분`;
}

/**
 * Format chart axis time based on time range
 * - Short range (< 1 day): HH:MM
 * - Medium range (< 1 week): MM/DD HH:MM
 * - Long range (>= 1 week): MM/DD or YY/MM/DD
 */
export function formatChartTime(date: Date | string, rangeHours?: number): string {
  const d = parseAsUTC(date);
  
  if (!rangeHours || rangeHours <= 24) {
    // Short range: show time only
    return d.toLocaleTimeString('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } else if (rangeHours <= 24 * 7) {
    // Medium range: show date and time
    return d.toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).replace(/\./g, '/').replace(' ', ' ');
  } else if (rangeHours <= 24 * 90) {
    // Long range (< 3 months): show date only
    return d.toLocaleDateString('ko-KR', {
      timeZone: 'Asia/Seoul',
      month: '2-digit',
      day: '2-digit',
    }).replace(/\./g, '/').replace(/\/$/, '');
  } else {
    // Very long range: show year/month/day
    return d.toLocaleDateString('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: '2-digit',
      month: '2-digit',
      day: '2-digit',
    }).replace(/\./g, '/').replace(/\/$/, '');
  }
}
