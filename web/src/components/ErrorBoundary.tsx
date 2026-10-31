import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Card } from "./ui";

/** Catches render crashes below it and offers a reload instead of a blank page. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info.componentStack); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Card className="space-y-2">
        <div role="alert" className="space-y-2">
          <h2 className="font-semibold">Something went wrong</h2>
          <p className="text-sm text-danger">{this.state.error.message}</p>
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </div>
      </Card>
    );
  }
}
