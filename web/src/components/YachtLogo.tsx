interface YachtLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function YachtLogo({ className = '', size = 'md' }: YachtLogoProps) {
  const sizes = {
    sm: 'w-8 h-8',
    md: 'w-11 h-11',
    lg: 'w-16 h-16',
  };

  return (
    <div className={`${sizes[size]} ${className} bg-gradient-to-br from-blue-500 via-blue-600 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/25`}>
      <svg 
        viewBox="0 0 24 24" 
        fill="none" 
        className="w-2/3 h-2/3"
        stroke="white" 
        strokeWidth="1.5" 
        strokeLinecap="round" 
        strokeLinejoin="round"
      >
        {/* Hull */}
        <path d="M2 19 L4 21 L20 21 L22 19 L18 19 L16 17 L8 17 L6 19 Z" fill="white" stroke="none" />
        
        {/* Main sail */}
        <path d="M12 4 L12 16 L19 16 Z" fill="white" fillOpacity="0.9" stroke="none" />
        
        {/* Jib sail */}
        <path d="M12 6 L12 14 L6 14 Z" fill="white" fillOpacity="0.7" stroke="none" />
        
        {/* Mast */}
        <line x1="12" y1="3" x2="12" y2="17" stroke="white" strokeWidth="1.5" />
        
        {/* Flag */}
        <path d="M12 3 L15 4.5 L12 6" fill="white" fillOpacity="0.9" stroke="none" />
      </svg>
    </div>
  );
}
