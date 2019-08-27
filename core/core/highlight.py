import re
from pygments import lex
from pygments.lexers import CLexer
from pygments.token import Comment, Keyword, Literal, Name, Operator, Punctuation, Text


class Highlight:
    def __init__(self, logger, src_file):
        self.logger = logger

        with open(src_file) as fp:
            src = fp.read()

        self.tokens = lex(src, CLexer())

        # Current token line number.
        self.cur_line_numb = 1
        # Current token start offset within current line.
        self.cur_start_offset = 0

        # List of entities (each represented as kind, line number, start and end offsets) to be highligted
        self.highlights = list()

    # Go to the next line, reset current token start offset and skip normal location update when meet new line symbol.
    def go_to_next_line(self, c='\n'):
        if c == '\n':
            self.cur_line_numb += 1
            self.cur_start_offset = 0
            return True
        else:
            return False

    # Simple token highlighting.
    def highligh_token(self, token_type, token_len):
        if not token_len:
            return

        self.highlights.append([
            # Get all capital letters from token type consisting of several parts.
            ''.join([''.join(re.findall("[A-Z]", k)) for k in tuple(token_type)]),
            self.cur_line_numb,
            self.cur_start_offset,
            self.cur_start_offset + token_len
        ])
        # Update current token start offset according to current token length.
        self.cur_start_offset += token_len

    def highlight(self):
        for token in self.tokens:
            token_type, token_text = tuple(token)
            token_len = len(token_text)

            # Handle token types that do not need special processing.
            if token_type in (
                Comment.PreprocFile,
                Keyword,
                Keyword.Type,
                Keyword.Reserved,
                Literal.Number.Hex,
                Literal.Number.Integer,
                Literal.Number.Oct,
                Literal.String,
                Literal.String.Char,
                Literal.String.Escape,
                Name,
                Name.Builtin,
                Name.Label,
                Operator
            ):
                self.highligh_token(token_type, token_len)
                continue
            # Trailing "\n" may be included into single line comment and preprocessor directives.
            elif token_type in (
                Comment,
                Comment.Preproc,
                Comment.Single
            ):
                if token_text[-1] == '\n':
                    self.highligh_token(token_type, token_len - 1)
                    self.go_to_next_line()
                    continue
                else:
                    self.highligh_token(token_type, token_len)
                    continue
            # Multiline comments include "\n".
            elif token_type is Comment.Multiline:
                cur_end_offset = self.cur_start_offset

                for c in token_text:
                    # Finish hanling of current comment line.
                    if c == '\n':
                        self.highligh_token(token_type, cur_end_offset - self.cur_start_offset)
                        self.go_to_next_line()
                        cur_end_offset = 0
                    else:
                        cur_end_offset += 1

                # Add last multiline comment line.
                self.highligh_token(token_type, cur_end_offset - self.cur_start_offset)
                continue
            # Highlighting for functions is performed together with building cross references.
            elif token_type is Name.Function:
                # Update current start offset for following tokens.
                self.cur_start_offset += token_len
                continue
            # There is no special highlighting for punctuation.
            elif token_type is Punctuation:
                # Update current start offset for following tokens.
                self.cur_start_offset += token_len
                continue
            # There is no special highlighting for text but there may be one or more "\n" at the beginning, in the
            # middle or at the end.
            elif token_type is Text:
                for c in token_text:
                    if not self.go_to_next_line(c):
                        # Update current start offset for following tokens.
                        self.cur_start_offset += 1

                continue
            else:
                self.logger.warning("Does not support token \"{0}\" of type \"{1}\"".format(token_text, token_type))
                continue

            raise RuntimeError("Token processing should not pass here")

    # In core.highlight.Highlight#highlight we assume that highlighted entity locations do not overlap. But there may
    # be other more important sources for highlighting, e.g. for cross referencing, so, we may need to remove overlaps.
    def extra_highlight(self, extra_highlights):
        # Remove previous less important highlights that are overlapped with extra ones.
        # Store highlights to be removed and remove them later at once rather than create new list of highlights each
        # time when some highlights should be removed. This should work much faster since we expect that there are very
        # many highlights and just few highlights should be removed
        highlights_to_be_removed = list()
        for extra_highlight in extra_highlights:
            extra_highlight_line_numb, extra_highlight_start_offset, extra_highlight_end_offset = extra_highlight[1:]

            for highlight in self.highlights:
                highlight_line_numb, highlight_start_offset, highlight_end_offset = highlight[1:]
                if highlight_line_numb == extra_highlight_line_numb:
                    if highlight_start_offset <= extra_highlight_end_offset \
                            and highlight_end_offset >= extra_highlight_start_offset:
                        highlights_to_be_removed.append(highlight)

        if highlights_to_be_removed:
            self.highlights = [highlight for highlight in self.highlights if highlight not in highlights_to_be_removed]

        # Add extra highlights.
        for extra_highlight in extra_highlights:
            self.highlights.append(extra_highlight)


# TODO: remove!!!
highlight = Highlight(None, '/home/novikov/work/klever-data/build bases/linux-3.14.79/Storage/home/novikov/work/klever-data/linux-stable/drivers/ata/pata_arasan_cf.c')
highlight.highlight()
for h in highlight.highlights:
    print(h)