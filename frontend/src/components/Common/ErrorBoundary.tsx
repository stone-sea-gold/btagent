import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="h-full flex items-center justify-center p-8"
          style={{ backgroundColor: 'var(--bg-primary)' }}
        >
          <div className="text-center max-w-md">
            <p className="text-lg mb-2" style={{ color: 'var(--danger)' }}>
              页面出错了
            </p>
            <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>
              {this.state.error?.message || '未知错误'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 rounded-lg text-sm"
              style={{ backgroundColor: 'var(--accent)', color: 'white' }}
            >
              重试
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
