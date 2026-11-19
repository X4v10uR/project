from rest_framework.renderers import JSONRenderer


class DownloadStatusRenderer(JSONRenderer):
    """Downloads use Django file responses. DRF errors and OPTIONS use JSON."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context['response']['Content-Type'] = 'application/json'
        return super().render(data, accepted_media_type, renderer_context)


class CalendarRenderer(DownloadStatusRenderer):
    media_type = 'text/calendar'
    format = 'ics'


class PDFRenderer(DownloadStatusRenderer):
    media_type = 'application/pdf'
    format = 'pdf'


class PNGRenderer(DownloadStatusRenderer):
    media_type = 'image/png'
    format = 'png'


class JPEGRenderer(DownloadStatusRenderer):
    media_type = 'image/jpeg'
    format = 'jpeg'


class CSVRenderer(DownloadStatusRenderer):
    media_type = 'text/csv'
    format = 'csv'


class ZipRenderer(DownloadStatusRenderer):
    media_type = 'application/zip'
    format = 'zip'
