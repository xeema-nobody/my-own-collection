import { Component, type ErrorInfo, type ReactNode } from "react";

/** Catches render crashes below it and offers a reload instead of a blank page. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info.componentStack); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="card space-y-2">
        <h2 className="font-semibold">Something went wrong</h2>
        <p className="text-sm text-red-500">{this.state.error.message}</p>
        <button className="btn" onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }
}
