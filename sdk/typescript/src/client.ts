export class SahoolClient {
  constructor(public baseUrl: string, public token: string) {}
  url(path: string): string {
    return `${this.baseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  }
  fields = { listUrl: () => this.url('/v1/fields') };
  recommendations = { baseUrl: () => this.url('/v1/recommendations') };
  ecosystem = { baseUrl: () => this.url('/v1/ecosystem') };
}
