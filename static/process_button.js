$(document).ready(function() {
   $('#goodButton, #badButton, #neutralButton, #absentButton, #nextButton').on('click', function() {
       var studentName = $('#studentName').text();
       console.log(studentName);
       var buttonValue = $(this).val();
       var courseCode = window.location.pathname.split('/').pop();
       $.ajax({
           url: '/response_quality',
           type: 'POST',
           data: {
              studentName: studentName,
              buttonValue: buttonValue,
              course: courseCode
           },
           success: function(response) {
              $('#studentName').text(response);
           },
           error: function(error) {
              console.log(error);
           }
       });
   });
});
