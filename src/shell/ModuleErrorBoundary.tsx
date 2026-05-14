import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useActiveModule } from '@/store/active-module'

interface ModuleErrorBoundaryProps {
  moduleId: string
  moduleName: string
  children: ReactNode
}

interface ModuleErrorBoundaryState {
  error: Error | null
  componentStack: string | null
}

class ModuleErrorBoundaryInner extends Component<
  ModuleErrorBoundaryProps & { onRecover: () => void },
  ModuleErrorBoundaryState
> {
  state: ModuleErrorBoundaryState = { error: null, componentStack: null }

  static getDerivedStateFromError(error: Error): Partial<ModuleErrorBoundaryState> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // componentStack is invaluable for minified React errors like #130
    // ("Element type is invalid"): without it the user sees `args=[object,""]`
    // and can't tell which component exported wrong. With it, we get the
    // owner-chain down to the exact JSX line.
    console.error(`[ModuleErrorBoundary] ${this.props.moduleId} crashed`, error, info)
    this.setState({ componentStack: info.componentStack ?? null })
  }

  componentDidUpdate(prevProps: ModuleErrorBoundaryProps) {
    if (prevProps.moduleId !== this.props.moduleId && this.state.error) {
      this.setState({ error: null, componentStack: null })
    }
  }

  render() {
    const { error, componentStack } = this.state
    if (!error) return this.props.children

    return (
      <div className="flex h-full w-full items-center justify-center bg-background p-8">
        <div className="max-w-2xl rounded-lg border border-border bg-card p-5 text-sm shadow-lg">
          <p className="text-base font-semibold text-foreground">
            {this.props.moduleName} could not open
          </p>
          <p className="mt-2 text-muted-foreground">
            ALOS caught this module failure so the rest of the shell can keep
            running. The module state was not reset.
          </p>
          <pre className="mt-4 max-h-40 overflow-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">
            {error.message}
          </pre>
          {componentStack && (
            <details className="mt-3">
              <summary className="cursor-pointer select-none text-xs font-medium text-muted-foreground hover:text-foreground">
                Component stack
              </summary>
              <pre className="mt-2 max-h-60 overflow-auto rounded-md bg-muted p-3 text-[11px] leading-snug text-muted-foreground">
                {componentStack.trim()}
              </pre>
            </details>
          )}
          {error.stack && (
            <details className="mt-2">
              <summary className="cursor-pointer select-none text-xs font-medium text-muted-foreground hover:text-foreground">
                Error stack
              </summary>
              <pre className="mt-2 max-h-60 overflow-auto rounded-md bg-muted p-3 text-[11px] leading-snug text-muted-foreground">
                {error.stack.trim()}
              </pre>
            </details>
          )}
          <button
            type="button"
            className="mt-4 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground"
            onClick={this.props.onRecover}
          >
            Return to Chat
          </button>
        </div>
      </div>
    )
  }
}

export function ModuleErrorBoundary(props: ModuleErrorBoundaryProps) {
  const setActive = useActiveModule((s) => s.setActive)
  return (
    <ModuleErrorBoundaryInner {...props} onRecover={() => setActive('chat')} />
  )
}
